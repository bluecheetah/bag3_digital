from typing import Any, Mapping, Optional, Type, List

from pybag.enum import RoundMode, MinLenMode

from bag.util.immutable import Param
from bag.design.module import Module
from bag.layout.template import TemplateDB
from bag.layout.routing.base import TrackID

from xbase.layout.enum import MOSWireType
from xbase.layout.mos.base import MOSBasePlaceInfo, MOSBase

from .gates import InvCore
from .current_starved_inv import CurrentStarvedInvCore
from ...schematic.inv_diff import bag3_digital__inv_diff


class InvDiffCore(MOSBase):
    """Differential inverter cell using inverters"""
    def __init__(self, temp_db: TemplateDB, params: Param, **kwargs: Any) -> None:
        MOSBase.__init__(self, temp_db, params, **kwargs)

    @classmethod
    def get_schematic_class(cls) -> Optional[Type[Module]]:
        return bag3_digital__inv_diff

    @classmethod
    def get_params_info(cls) -> Mapping[str, str]:
        return dict(
            pinfo='The MOSBasePlaceInfo object.',
            seg_drv='number of segments of inverter.',
            seg_kp='number of segments of keeper.',
            w_p='pmos width.',
            w_n='nmos width.',
            ridx_p='pmos row index.',
            ridx_n='nmos row index.',
            dummy_dev='True to add dummy devices around active devices.',
            chain='True to set up inputs to allow for chaining.',
            sig_locs='Signal track location dictionary.',
            vertical_in='True to have inputs on vertical layer; True by default',
            sep_vert_in='True to use separate vertical tracks for in and inb; False by default',
            sep_vert_out='True to use separate vertical tracks for out and outb; False by default',
            driver_tile_idx='Tile index of drivers; [1, 3] by default',
            ptap_tile_idx='Tile index of ptap; [0, 4] by default',
            ntap_tile_idx='Tile index of ntap; [2] by default',
        )

    @classmethod
    def get_default_param_values(cls) -> Mapping[str, Any]:
        return dict(
            w_p=0,
            w_n=0,
            ridx_p=-1,
            ridx_n=0,
            chain=False,
            dummy_dev=False,
            sig_locs=None,
            sep_vert_in=False,
            sep_vert_out=False,
            vertical_in=False,
            driver_tile_idx=[1, 3],
            ptap_tile_idx=[0, 4],
            ntap_tile_idx=[2],
        )

    def draw_layout(self) -> None:
        pinfo = MOSBasePlaceInfo.make_place_info(self.grid, self.params['pinfo'])
        self.draw_base(pinfo)

        w_p: int = self.params['w_p']
        w_n: int = self.params['w_n']
        ridx_p: int = self.params['ridx_p']
        ridx_n: int = self.params['ridx_n']
        sig_locs: Optional[Mapping[str, float]] = self.params['sig_locs']
        dummy_dev: bool = self.params['dummy_dev']
        vertical_in: bool = self.params['vertical_in']
        sep_vert_in: bool = self.params['sep_vert_in']
        sep_vert_in = sep_vert_in and vertical_in
        sep_vert_out: bool = self.params['sep_vert_out']
        seg_kp: int = self.params['seg_kp']
        seg_drv: int = self.params['seg_drv']
        chain: bool = self.params['chain']

        driver_tile_idx: List[int] = self.params['driver_tile_idx']
        ptap_tile_idx: List[int] = self.params['ptap_tile_idx']
        ntap_tile_idx: List[int] = self.params['ntap_tile_idx']

        if sig_locs is None: sig_locs = {}

        # --- make masters --- #

        # get tracks
        pg0_tidx = self.get_track_index(ridx_p, MOSWireType.G, 'sig', 0, tile_idx=driver_tile_idx[0])
        ng0_tidx = self.get_track_index(ridx_n, MOSWireType.G, 'sig', 0, tile_idx=driver_tile_idx[0])
        ng1_tidx = self.get_track_index(ridx_n, MOSWireType.G, 'sig', 1, tile_idx=driver_tile_idx[1])

        drv_in_loc = ng0_tidx if chain else sig_locs.get('in', None)
        kp_in_loc = sig_locs.get('kp_in', None)

        # Input inverters
        inv_drv_params = dict(pinfo=self.get_tile_pinfo(driver_tile_idx[0]), seg=seg_drv, w_p=w_p, w_n=w_n,
                              ridx_p=ridx_p, ridx_n=ridx_n, vertical_out=False,
                              vertical_sup=True, sig_locs={'nin': drv_in_loc})
        inv_drv_master = self.new_template(InvCore, params=inv_drv_params)
        inv_drv_ncols = inv_drv_master.num_cols

        # Keeper inverters
        inv_kp_params = dict(pinfo=self.get_tile_pinfo(driver_tile_idx[0]), seg=seg_kp, w_p=w_p, w_n=w_n,
                             ridx_p=ridx_p, ridx_n=ridx_n, vertical_out=False,
                             vertical_sup=True, sig_locs={'nin': kp_in_loc})
        inv_kp_master = self.new_template(InvCore, params=inv_kp_params)
        inv_kp_ncols = inv_kp_master.num_cols

        # --- Placement --- #
        blk_sp = self.min_sep_col
        if sep_vert_in:
            cur_col = blk_sp
        elif dummy_dev:
            cur_col = 2
        else:
            cur_col = 0
        inv_in = self.add_tile(inv_drv_master, driver_tile_idx[0], cur_col)
        inv_inb = self.add_tile(inv_drv_master, driver_tile_idx[1], cur_col)

        if ~(inv_drv_ncols % 2) and ~(inv_kp_ncols % 2):
            cur_col += inv_drv_ncols + inv_kp_ncols
        else:
            cur_col += inv_drv_ncols + blk_sp + inv_kp_ncols
        inv_fb0 = self.add_tile(inv_kp_master, driver_tile_idx[0], cur_col, flip_lr=True)
        inv_fb1 = self.add_tile(inv_kp_master, driver_tile_idx[1], cur_col, flip_lr=True)

        if dummy_dev:
            pdummy, ndummy0, ndummy1 = [], [], []
            pdummy.append(self.add_mos(ridx_p, 0, 2, tile_idx=driver_tile_idx[0]))
            ndummy0.append(self.add_mos(ridx_n, 0, 2, tile_idx=driver_tile_idx[0]))
            pdummy.append(self.add_mos(ridx_p, 0, 2, tile_idx=driver_tile_idx[1]))
            ndummy1.append(self.add_mos(ridx_n, 0, 2, tile_idx=driver_tile_idx[1]))

            # self.add_mos(ridx_p, inv_drv_ncols + 3, 2, tile_idx=0)
            # self.add_mos(ridx_n, inv_drv_ncols + 3, 2, tile_idx=0)
            # self.add_mos(ridx_p, inv_drv_ncols + 3, 2, tile_idx=1)
            # self.add_mos(ridx_n, inv_drv_ncols + 3, 2, tile_idx=1)

            pdummy.append(self.add_mos(ridx_p, cur_col, 2, tile_idx=driver_tile_idx[0]))
            ndummy0.append(self.add_mos(ridx_n, cur_col, 2, tile_idx=driver_tile_idx[0]))
            pdummy.append(self.add_mos(ridx_p, cur_col, 2, tile_idx=driver_tile_idx[1]))
            ndummy1.append(self.add_mos(ridx_n, cur_col, 2, tile_idx=driver_tile_idx[1]))

        cur_col += (blk_sp * sep_vert_out)
        # add ptaps
        vss0_ports = self.add_substrate_contact(0, 0, tile_idx=ptap_tile_idx[0], seg=cur_col)
        vss1_ports = self.add_substrate_contact(0, 0, tile_idx=ptap_tile_idx[1], seg=cur_col)

        # add ntap
        vdd_ports = self.add_substrate_contact(0, 0, tile_idx=ntap_tile_idx[0], seg=cur_col)

        self.set_mos_size()

        # --- Routing --- #
        # supplies
        vdd_tid = self.get_track_id(0, MOSWireType.DS, 'sup', 0, tile_idx=ntap_tile_idx[0])
        vss0_tid = self.get_track_id(0, MOSWireType.DS, 'sup', 0, tile_idx=ptap_tile_idx[0])
        vss1_tid = self.get_track_id(0, MOSWireType.DS, 'sup', 0, tile_idx=ptap_tile_idx[1])

        vdd = self.connect_to_tracks(vdd_ports, vdd_tid)
        vss0 = self.connect_to_tracks(vss0_ports, vss0_tid)
        vss1 = self.connect_to_tracks(vss1_ports, vss1_tid)

        self.add_pin('VDD', vdd, connect=True)
        self.add_pin('VSS', self.connect_wires([vss0, vss1]), connect=True)

        for inst in (inv_in, inv_fb0):
            self.connect_to_track_wires(inst.get_pin('VSS'), vss0)
            self.connect_to_track_wires(inst.get_pin('VDD'), vdd)
        for inst in (inv_inb, inv_fb1):
            self.connect_to_track_wires(inst.get_pin('VSS'), vss1)
            self.connect_to_track_wires(inst.get_pin('VDD'), vdd)
        if dummy_dev:
                for mos in pdummy:
                    self.connect_to_track_wires(mos.s, vdd)
                for mos in ndummy0:
                    self.connect_to_track_wires(mos.s, vss0)
                for mos in ndummy1:
                    self.connect_to_track_wires(mos.s, vss1)

        hm_layer = self.conn_layer + 1
        vm_layer = hm_layer + 1

        # input pins on vm_layer
        w_sig_vm = self.tr_manager.get_width(vm_layer, 'sig')
        if vertical_in:
            close_track = self.grid.coord_to_track(inv_in.get_pin('nin').lower,
                                                   vm_layer,
                                                   RoundMode.NEAREST)
            _, vm_locs = self.tr_manager.place_wires(vm_layer, ['sig', 'sig'],
                                                     close_track, -1)
            if sep_vert_in:
                tidx0, tidx1 = vm_locs[0], vm_locs[1]
            else:
                tidx0, tidx1 = vm_locs[1], vm_locs[1]
            in_vm = self.connect_to_tracks(inv_in.get_pin('nin'),
                                           TrackID(vm_layer, tidx0, w_sig_vm),
                                           min_len_mode=MinLenMode.MIDDLE)
            self.add_pin('in', in_vm)
            inb_vm = self.connect_to_tracks(inv_inb.get_pin('nin'),
                                            TrackID(vm_layer, tidx1, w_sig_vm),
                                            min_len_mode=MinLenMode.MIDDLE)
            self.add_pin('inb', inb_vm)
        else:
            self.reexport(inv_in.get_port('nin'), net_name='in', hide=False)
            self.reexport(inv_inb.get_port('nin'), net_name='inb', hide=False)

        # outputs on vm_layer
        _tidx1 = self.grid.coord_to_track(vm_layer,
                                          cur_col * self.sd_pitch,
                                          RoundMode.NEAREST)

        # get vm_layer tracks for mid and midb
        mid_coord = inv_in.get_pin('nin').upper
        mid_tidx = self.grid.coord_to_track(vm_layer, mid_coord,
                                            RoundMode.NEAREST)
        mid_tidx = self.tr_manager.get_next_track(vm_layer, mid_tidx,
                                                  'sig', 'sig', 1)
        _, vm_locs = self.tr_manager.place_wires(vm_layer,
                                                 ['sig', 'sig'],
                                                 mid_tidx)
        ext_list = []
        mid = self.connect_to_tracks([inv_in.get_pin('pout'),
                                      inv_in.get_pin('nout'),
                                      inv_fb0.get_pin('pout'),
                                      inv_fb0.get_pin('nout'),
                                      inv_fb1.get_pin('pin')],
                                      TrackID(vm_layer, vm_locs[1], w_sig_vm), ret_wire_list=ext_list)
        midb = self.connect_to_tracks([inv_inb.get_pin('pout'),
                                       inv_inb.get_pin('nout'),
                                       inv_fb1.get_pin('pout'),
                                       inv_fb1.get_pin('nout'),
                                       inv_fb0.get_pin('pin')],
                                       TrackID(vm_layer, vm_locs[-2], w_sig_vm))
        # make the horizontal wires the same length to match capacitance
        self.add_pin('mid', mid, hide=True)
        self.add_pin('midb', midb, hide=True)
        self.extend_wires(inv_fb1.get_pin('nout'), upper=ext_list[0].upper)

        # draw output pins
        if not sep_vert_out or chain:
            out = self.connect_to_tracks(mid,
                                        inv_in.get_pin('in').track_id,
                                        min_len_mode=MinLenMode.MIDDLE)
            outb = self.connect_to_tracks(midb,
                                         inv_inb.get_pin('in').track_id,
                                         min_len_mode=MinLenMode.MIDDLE)
        else:
            out = mid
            outb = midb

        self.add_pin('out', out, label='out')
        self.add_pin('outb', outb, label='outb')

        # breakpoint()

        # get schematic parameters
        self.sch_params = dict(
            inv_in=inv_drv_master.sch_params,
            inv_fb=inv_kp_master.sch_params,
            dummy_dev=dummy_dev,
            dummy_params=dict(
                wn=self.get_tile_pinfo(driver_tile_idx[0]).get_row_place_info(ridx_n).row_info.width,
                wp=self.get_tile_pinfo(driver_tile_idx[0]).get_row_place_info(ridx_p).row_info.width,
                lch=self.get_tile_pinfo(driver_tile_idx[0]).get_row_place_info(ridx_p).row_info.lch,
                seg=2,
                intent=self.get_tile_pinfo(driver_tile_idx[0]).get_row_place_info(ridx_p).row_info.threshold,
            )
        )

class CurrentStarvedInvDiffCore(MOSBase):
    """Differential inverter cell using current-starved inverters"""
    def __init__(self, temp_db: TemplateDB, params: Param, **kwargs: Any) -> None:
        MOSBase.__init__(self, temp_db, params, **kwargs)

    @classmethod
    def get_schematic_class(cls) -> Optional[Type[Module]]:
        return bag3_digital__inv_diff

    @classmethod
    def get_params_info(cls) -> Mapping[str, str]:
        return dict(
            pinfo='The MOSBasePlaceInfo object.',
            seg_drv='number of segments of driver inverter.',
            seg_mir='number of segments of current mirror.',
            seg_kp='number of segments of keeper.',
            w_p='pmos width.',
            w_n='nmos width.',
            cs_ridx_p='pmos current starved row index.',
            cs_ridx_n='nmos current starved row index.',
            ridx_p='pmos row index.',
            ridx_n='nmos row index.',
            ridx_mir='mirror row index.',
            sig_locs='Signal track location dictionary.',
            vertical_in='True to have inputs on vertical layer; True by default',
            sep_vert_in='True to use separate vertical tracks for in and inb; False by default',
            sep_vert_out='True to use separate vertical tracks for out and outb; False by default',
            draw_mir='True to draw current mirror device; True by default',
            ptap_tile_idx='Ptap tile index.',
            ntap_tile_idx='Ntap tile index.',
            inv_tile_idx='Inverter tile index.',
        )

    @classmethod
    def get_default_param_values(cls) -> Mapping[str, Any]:
        return dict(
            w_p=0,
            w_n=0,
            cs_ridx_p=-2,
            cs_ridx_n=2,
            ridx_p=-1,
            ridx_n=1,
            ridx_mir=0,
            seg_mir=1,
            sig_locs=None,
            sep_vert_in=False,
            sep_vert_out=False,
            vertical_in=False,
            draw_mir=True,
            ptap_tile_idx=[0,4],
            ntap_tile_idx=2,
            inv_tile_idx=[1,3],
        )

    def draw_layout(self) -> None:
        pinfo = MOSBasePlaceInfo.make_place_info(self.grid, self.params['pinfo'])
        self.draw_base(pinfo)

        w_p: int = self.params['w_p']
        w_n: int = self.params['w_n']
        ridx_p: int = self.params['ridx_p']
        ridx_n: int = self.params['ridx_n']
        ridx_mir: int = self.params['ridx_mir']
        # sig_locs: Optional[Mapping[str, float]] = self.params['sig_locs']
        vertical_in: bool = self.params['vertical_in']
        sep_vert_in: bool = self.params['sep_vert_in']
        sep_vert_in = sep_vert_in and vertical_in
        sep_vert_out: bool = self.params['sep_vert_out']
        seg_kp: int = self.params['seg_kp']
        seg_drv: int = self.params['seg_drv']
        seg_mir: int = self.params['seg_mir']

        draw_mir: bool = self.params['draw_mir']

        ptap_tile_idx: List[int] = self.params['ptap_tile_idx']
        ntap_tile_idx: int = self.params['ntap_tile_idx']
        inv_tile_idx: List[int] = self.params['inv_tile_idx']

        # --- make masters --- #
        # Input inverters
        inv_drv_params = dict(pinfo=self.get_tile_pinfo(inv_tile_idx[0]),
                              seg_inv=seg_drv, seg_mir=seg_mir, draw_mir=draw_mir,
                              ridx_p=ridx_p, ridx_n_inv=ridx_n, ridx_n_mir=ridx_mir,)
        inv_drv_master = self.new_template(CurrentStarvedInvCore, params=inv_drv_params)
        inv_drv_ncols = inv_drv_master.num_cols

        in_warr = inv_drv_master.get_port('in').get_pins()[0]
        ref_tidx = in_warr.track_id.base_index
        ng1_tidx = self.tr_manager.get_next_track(2, ref_tidx, 'sig', 'sig', up=2)

        n_ds1_tidx = inv_drv_master.get_port('nout').get_pins()[0].track_id.base_index

        # Keeper inverters
        inv_kp_params = dict(pinfo=self.get_tile_pinfo(inv_tile_idx[0]), seg=seg_kp,
                             ridx_p=ridx_p, ridx_n=ridx_n, vertical_out=False, vertical_in=True,
                             sig_locs={'nin': ng1_tidx,
                                       'nout': n_ds1_tidx,},
                             vertical_sup=True)
        inv_kp_master = self.new_template(InvCore, params=inv_kp_params)
        inv_kp_ncols = inv_kp_master.num_cols

        # --- Placement --- #
        blk_sp = self.min_sep_col

        cur_col = blk_sp if sep_vert_in else 0
        inv_in = self.add_tile(inv_drv_master, inv_tile_idx[0], cur_col)
        inv_inb = self.add_tile(inv_drv_master, inv_tile_idx[1], cur_col)

        cur_col += inv_drv_ncols + blk_sp + inv_kp_ncols
        # Column parity check to avoid drc violation
        if cur_col % 2: cur_col += 1
        inv_fb0 = self.add_tile(inv_kp_master, inv_tile_idx[0], cur_col, flip_lr=True)
        inv_fb1 = self.add_tile(inv_kp_master, inv_tile_idx[1], cur_col, flip_lr=True)

        cur_col += (blk_sp * sep_vert_out)

        vss_bot_ports = self.add_substrate_contact(0, 0, tile_idx=ptap_tile_idx[0], seg=cur_col)
        vdd_ports = self.add_substrate_contact(0, 0, tile_idx=ntap_tile_idx, seg=cur_col)
        vss_top_ports = self.add_substrate_contact(0, 0, tile_idx=ptap_tile_idx[1], seg=cur_col)

        self.set_mos_size(cur_col)

        # --- Routing --- #
        # supplies
        if draw_mir:
            vss_tie_top_list = [inv_inb.get_pin('VSS'), inv_fb1.get_pin('VSS'),
                                vss_top_ports]
            vss_tie_bot_list = [inv_in.get_pin('VSS'), inv_fb0.get_pin('VSS'),
                                vss_bot_ports]
            vdd_tie_list = [inv_in.get_pin('VDD'), inv_inb.get_pin('VDD'),
                            inv_fb0.get_pin('VDD'), inv_fb1.get_pin('VDD'),
                            vdd_ports]
        else:
            vss_tie_bot_list = [vss_bot_ports]
            vss_tie_top_list = [vss_top_ports]
            vdd_tie_list = [inv_in.get_pin('VDD'), inv_inb.get_pin('VDD'),
                            inv_fb0.get_pin('VDD'), inv_fb1.get_pin('VDD'),
                            vdd_ports]
            self.add_pin('VSS_int_bot', self.connect_wires([inv_in.get_pin('VSS_int'), inv_fb0.get_pin('VSS')]), show=True, connect=True)
            self.add_pin('VSS_int_top', self.connect_wires([inv_inb.get_pin('VSS_int'), inv_fb1.get_pin('VSS')]), show=True, connect=True)
            self.add_pin('VSS_bot_taps', vss_bot_ports, hide=True)
            self.add_pin('VSS_top_taps', vss_top_ports, hide=True)

        vss_top_tie = self.connect_wires(vss_tie_top_list)
        vss_bot_tie = self.connect_wires(vss_tie_bot_list)
        vdd_tie = self.connect_wires(vdd_tie_list)

        vdd_tid = self.get_track_id(0, MOSWireType.DS_GATE, 'sup', tile_idx=ntap_tile_idx)
        vss_top_tid = self.get_track_id(0, MOSWireType.DS_GATE, 'sup', tile_idx=ptap_tile_idx[1])
        vss_bot_tid = self.get_track_id(0, MOSWireType.DS_GATE, 'sup', tile_idx=ptap_tile_idx[0])

        vdd_list = [self.connect_to_tracks(vdd_tie, vdd_tid)]
        vss_list = [self.connect_to_tracks(vss_top_tie, vss_top_tid),
                    self.connect_to_tracks(vss_bot_tie, vss_bot_tid)]

        self.add_pin('VDD', vdd_list)
        self.add_pin('VSS', vss_list)

        hm_layer = self.conn_layer + 1
        vm_layer = hm_layer + 1

        # input pins on vm_layer
        w_sig_vm = self.tr_manager.get_width(vm_layer, 'sig')
        if vertical_in:
            close_track = self.grid.coord_to_track(inv_in.get_pin('nin').lower,
                                                   vm_layer,
                                                   RoundMode.NEAREST)
            _, vm_locs = self.tr_manager.place_wires(vm_layer, ['sig', 'sig'],
                                                     close_track, -1)
            if sep_vert_in:
                tidx0, tidx1 = vm_locs[0], vm_locs[1]
            else:
                tidx0, tidx1 = vm_locs[1], vm_locs[1]
            in_vm = self.connect_to_tracks(inv_in.get_pin('nin'),
                                           TrackID(vm_layer, tidx0, w_sig_vm),
                                           min_len_mode=MinLenMode.MIDDLE)
            self.add_pin('in', in_vm)
            inb_vm = self.connect_to_tracks(inv_inb.get_pin('nin'),
                                            TrackID(vm_layer, tidx1, w_sig_vm),
                                            min_len_mode=MinLenMode.MIDDLE)
            self.add_pin('inb', inb_vm)
        else:
            self.reexport(inv_in.get_port('nin'), net_name='in', hide=False)
            self.reexport(inv_inb.get_port('nin'), net_name='inb', hide=False)
            if draw_mir:
                self.reexport(inv_in.get_port('ref_v'), net_name='ref_v_bot', hide=False)
                self.reexport(inv_inb.get_port('ref_v'), net_name='ref_v_top', hide=False)

        # outputs on vm_layer
        _tidx1 = self.grid.coord_to_track(vm_layer,
                                          cur_col * self.sd_pitch,
                                          RoundMode.NEAREST)
        if sep_vert_out:
            raise NotImplementedError('Not implemented yet.')

        # get vm_layer tracks for mid and midb
        mid_coord = inv_in.get_pin('nin').upper
        mid_tidx = self.grid.coord_to_track(vm_layer, mid_coord,
                                            RoundMode.NEAREST)
        mid_tidx = self.tr_manager.get_next_track(vm_layer, mid_tidx,
                                                  'sig', 'sig', 1)
        _, vm_locs = self.tr_manager.place_wires(vm_layer,
                                                 ['sig', 'sig'],
                                                 mid_tidx)
        mid = self.connect_to_tracks([inv_in.get_pin('pout'),
                                      inv_in.get_pin('nout'),
                                     inv_fb0.get_pin('pout'),
                                     inv_fb0.get_pin('nout'),
                                     inv_fb1.get_pin('nin')],
                                     TrackID(vm_layer, vm_locs[1], w_sig_vm))
        midb = self.connect_to_tracks([inv_inb.get_pin('pout'),
                                       inv_inb.get_pin('nout'),
                                      inv_fb1.get_pin('pout'),
                                      inv_fb1.get_pin('nout'),
                                      inv_fb0.get_pin('nin')],
                                      TrackID(vm_layer, vm_locs[-2], w_sig_vm))

        # draw output pins
        out_hm = self.connect_to_tracks(mid,
                                        inv_in.get_pin('nin').track_id,
                                        min_len_mode=MinLenMode.MIDDLE)
        outb_hm = self.connect_to_tracks(midb,
                                         inv_inb.get_pin('nin').track_id,
                                         min_len_mode=MinLenMode.MIDDLE)
        self.add_pin('mid', mid, hide=True)
        self.add_pin('midb', midb, hide=True)
        self.add_pin('out', out_hm, label='out')
        self.add_pin('outb', outb_hm, label='outb')

        # get schematic parameters
        self.sch_params = dict(
            inv_in=inv_drv_master.sch_params,
            inv_fb=inv_kp_master.sch_params,
        )