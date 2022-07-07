from typing import Any, Mapping, Optional, Type

from pybag.enum import RoundMode, MinLenMode

from bag.util.immutable import Param
from bag.design.module import Module
from bag.layout.template import TemplateDB
from bag.layout.routing.base import TrackID

from xbase.layout.enum import MOSWireType
from xbase.layout.mos.base import MOSBasePlaceInfo, MOSBase

from .gates import InvCore, InvTristateCore
from ...schematic.latch_diff import bag3_digital__latch_diff


class LatchDiffCore(MOSBase):
    """Differential latch using tristate inverters"""
    def __init__(self, temp_db: TemplateDB, params: Param, **kwargs: Any) -> None:
        MOSBase.__init__(self, temp_db, params, **kwargs)

    @classmethod
    def get_schematic_class(cls) -> Optional[Type[Module]]:
        return bag3_digital__latch_diff

    @classmethod
    def get_params_info(cls) -> Mapping[str, str]:
        return dict(
            pinfo='The MOSBasePlaceInfo object.',
            seg='number of segments of output inverter.',
            w_p='pmos width.',
            w_n='nmos width.',
            ridx_p='pmos row index.',
            ridx_n='nmos row index.',
            sig_locs='Signal track location dictionary.',
            fanout_in='input stage fanout.',
            fanout_kp='keeper stage fanout.',
            vertical_in='True to have inputs on vertical layer; True by default',
            sep_vert_in='True to use separate vertical tracks for in and inb; False by default',
            sep_vert_out='True to use separate vertical tracks for out and outb; False by default',
        )

    @classmethod
    def get_default_param_values(cls) -> Mapping[str, Any]:
        return dict(
            w_p=0,
            w_n=0,
            ridx_p=-1,
            ridx_n=0,
            sig_locs=None,
            fanout_in=4,
            fanout_kp=8,
            sep_vert_in=False,
            sep_vert_out=False,
            vertical_in=True,
        )

    def draw_layout(self) -> None:
        pinfo = MOSBasePlaceInfo.make_place_info(self.grid, self.params['pinfo'])
        self.draw_base(pinfo)

        seg: int = self.params['seg']
        w_p: int = self.params['w_p']
        w_n: int = self.params['w_n']
        ridx_p: int = self.params['ridx_p']
        ridx_n: int = self.params['ridx_n']
        # sig_locs: Optional[Mapping[str, float]] = self.params['sig_locs']
        fanout_in: float = self.params['fanout_in']
        fanout_kp: float = self.params['fanout_kp']
        vertical_in: bool = self.params['vertical_in']
        sep_vert_in: bool = self.params['sep_vert_in']
        sep_vert_in = sep_vert_in and vertical_in
        sep_vert_out: bool = self.params['sep_vert_out']

        # --- make masters --- #
        # get tracks
        pg1_tidx = self.get_track_index(ridx_p, MOSWireType.G, 'sig', -1)
        pg0_tidx = self.get_track_index(ridx_p, MOSWireType.G, 'sig', -2)
        ng1_tidx = self.get_track_index(ridx_n, MOSWireType.G, 'sig', 1)
        ng0_tidx = self.get_track_index(ridx_n, MOSWireType.G, 'sig', 0)

        # output inverters
        inv_params = dict(pinfo=pinfo, seg=seg, w_p=w_p, w_n=w_n, ridx_p=ridx_p, ridx_n=ridx_n, vertical_out=False,
                          sig_locs={'nin': ng1_tidx})
        inv_master = self.new_template(InvCore, params=inv_params)
        inv_ncols = inv_master.num_cols

        # feedback tristate inverters
        seg_t1 = max(1, int(round(seg / (2 * fanout_kp))) * 2)
        tinv1_params = dict(pinfo=pinfo, seg=seg_t1, w_p=w_p, w_n=w_n, ridx_p=ridx_p, ridx_n=ridx_n, vertical_out=False,
                            sig_locs={'nin': pg0_tidx, 'nen': ng0_tidx, 'pen': pg1_tidx})
        tinv1_master = self.new_template(InvTristateCore, params=tinv1_params)
        tinv1_ncols = tinv1_master.num_cols

        # input tristate inverters
        seg_t0 = max(2 * seg_t1, max(2, int(round(seg / (2 * fanout_in))) * 2))
        tinv0_params = dict(pinfo=pinfo, seg=seg_t0, w_p=w_p, w_n=w_n, ridx_p=ridx_p, ridx_n=ridx_n, vertical_out=False,
                            sig_locs={'nin': pg1_tidx, 'nen': ng1_tidx, 'pen': pg0_tidx})
        tinv0_master = self.new_template(InvTristateCore, params=tinv0_params)
        tinv0_ncols = tinv0_master.num_cols

        # --- Placement --- #
        blk_sp = self.min_sep_col
        cur_col = blk_sp if sep_vert_in else 0
        tinv_in = self.add_tile(tinv0_master, 0, cur_col)
        tinv_inb = self.add_tile(tinv0_master, 1, cur_col)

        cur_col += tinv0_ncols + blk_sp + tinv1_ncols
        tinv_fb0 = self.add_tile(tinv1_master, 0, cur_col, flip_lr=True)
        tinv_fb1 = self.add_tile(tinv1_master, 1, cur_col, flip_lr=True)

        cur_col += blk_sp
        inv_out = self.add_tile(inv_master, 0, cur_col)
        inv_outb = self.add_tile(inv_master, 1, cur_col)

        cur_col += (inv_ncols + blk_sp) if sep_vert_out else inv_ncols
        self.set_mos_size(cur_col)

        # --- Routing --- #
        # supplies
        vss_list, vdd_list = [], []
        for inst in (tinv_in, tinv_inb, tinv_fb0, tinv_fb1, inv_out, inv_outb):
            vss_list.append(inst.get_pin('VSS'))
            vdd_list.append(inst.get_pin('VDD'))
        self.add_pin('VDD', self.connect_wires(vdd_list)[0])
        self.add_pin('VSS', self.connect_wires(vss_list)[0])

        # clkb on vm_layer
        hm_layer = self.conn_layer + 1
        vm_layer = hm_layer + 1

        w_clk_vm = self.tr_manager.get_width(vm_layer, 'clk')
        clkb_hm = tinv_in.get_pin('enb')
        clkb_vm_tidx = self.grid.coord_to_track(vm_layer, clkb_hm.middle, RoundMode.NEAREST)
        clkb_vm = self.connect_to_tracks([clkb_hm, tinv_inb.get_pin('enb'), tinv_fb0.get_pin('en'),
                                          tinv_fb1.get_pin('en')], TrackID(vm_layer, clkb_vm_tidx, w_clk_vm))
        self.add_pin('clkb', clkb_vm)

        # clk on vm_layer
        clk_hm = tinv_fb0.get_pin('enb')
        clk_vm_tidx = self.grid.coord_to_track(vm_layer, clk_hm.middle, RoundMode.GREATER)
        clk_vm = self.connect_to_tracks([tinv_in.get_pin('en'), tinv_inb.get_pin('en'), clk_hm,
                                         tinv_fb1.get_pin('enb')], TrackID(vm_layer, clk_vm_tidx, w_clk_vm))
        self.add_pin('clk', clk_vm)

        # input pins on vm_layer
        w_sig_vm = self.tr_manager.get_width(vm_layer, 'sig')
        if vertical_in:
            _, vm_locs = self.tr_manager.place_wires(vm_layer, ['sig', 'sig', 'clk'], clkb_vm_tidx, -1)
            if sep_vert_in:
                tidx0, tidx1 = vm_locs[0], vm_locs[1]
            else:
                tidx0, tidx1 = vm_locs[1], vm_locs[1]
            in_vm = self.connect_to_tracks(tinv_in.get_pin('nin'), TrackID(vm_layer, tidx0, w_sig_vm),
                                           min_len_mode=MinLenMode.MIDDLE)
            self.add_pin('in', in_vm)
            inb_vm = self.connect_to_tracks(tinv_inb.get_pin('nin'), TrackID(vm_layer, tidx1, w_sig_vm),
                                            min_len_mode=MinLenMode.MIDDLE)
            self.add_pin('inb', inb_vm)
        else:
            self.reexport(tinv_in.get_port('nin'), net_name='in', hide=False)
            self.reexport(tinv_inb.get_port('nin'), net_name='inb', hide=False)

        # outputs on vm_layer
        _tidx1 = self.grid.coord_to_track(vm_layer, cur_col * self.sd_pitch, RoundMode.NEAREST)
        if sep_vert_out:
            _tidx0 = self.tr_manager.get_next_track(vm_layer, _tidx1, 'sig', 'sig', -1)
        else:
            _tidx0 = _tidx1
        out_vm = self.connect_to_tracks([inv_out.get_pin('pout'), inv_out.get_pin('nout')],
                                        TrackID(vm_layer, _tidx0, w_sig_vm))
        self.add_pin('out', out_vm)
        outb_vm = self.connect_to_tracks([inv_outb.get_pin('pout'), inv_outb.get_pin('nout')],
                                         TrackID(vm_layer, _tidx1, w_sig_vm))
        self.add_pin('outb', outb_vm)

        # get vm_layer tracks for mid and midb
        vm_locs = self.tr_manager.spread_wires(vm_layer, ['clk', 'sig', 'sig', 'sig'], clk_vm_tidx, _tidx0,
                                               ('sig', 'sig'))
        self.connect_to_tracks([tinv_in.get_pin('pout'), tinv_in.get_pin('nout'), inv_out.get_pin('nin'),
                                tinv_fb0.get_pin('pout'), tinv_fb0.get_pin('nout'), tinv_fb1.get_pin('nin')],
                               TrackID(vm_layer, vm_locs[1], w_sig_vm))
        self.connect_to_tracks([tinv_inb.get_pin('pout'), tinv_inb.get_pin('nout'), inv_outb.get_pin('nin'),
                                tinv_fb1.get_pin('pout'), tinv_fb1.get_pin('nout'), tinv_fb0.get_pin('nin')],
                               TrackID(vm_layer, vm_locs[-2], w_sig_vm))

        # get schematic parameters
        self.sch_params = dict(
            tinv_in=tinv0_master.sch_params,
            tinv_fb=tinv1_master.sch_params,
            inv_out=inv_master.sch_params,
        )
