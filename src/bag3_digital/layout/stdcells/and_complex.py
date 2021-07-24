"""This module contains layout generators for complex AND gate with 2 - 9 inputs"""

from typing import Mapping, Any, Optional, Type, Sequence

from pybag.enum import MinLenMode, RoundMode

from bag.util.immutable import Param
from bag.design.module import Module
from bag.layout.template import TemplateDB
from bag.layout.routing.base import TrackID

from xbase.layout.enum import MOSWireType
from xbase.layout.mos.base import MOSBasePlaceInfo, MOSBase

from .gates import NAND2Core, NAND3Core, NOR2Core, NOR3Core, InvCore

from ...schematic.and_complex import bag3_digital__and_complex


class AndComplexRow(MOSBase):
    def __init__(self, temp_db: TemplateDB, params: Param, **kwargs: Any) -> None:
        MOSBase.__init__(self, temp_db, params, **kwargs)
        num_in: int = params['num_in']
        self._nand_in_list = get_nand_in_list(num_in)

    @property
    def nand_in_list(self) -> Sequence[int]:
        return self._nand_in_list

    @classmethod
    def get_schematic_class(cls) -> Optional[Type[Module]]:
        return bag3_digital__and_complex

    @classmethod
    def get_params_info(cls) -> Mapping[str, str]:
        return dict(
            pinfo='The MOSBasePlaceInfo object.',
            seg_dict='Dictionary of segments of standard cell components',
            num_in='Number of inputs',
            export_outb='True to export outb; True by default',
        )

    @classmethod
    def get_default_param_values(cls) -> Mapping[str, Any]:
        return dict(export_outb=True)

    def draw_layout(self) -> None:
        pinfo = MOSBasePlaceInfo.make_place_info(self.grid, self.params['pinfo'])
        self.draw_base(pinfo)

        seg_dict: Mapping[str, int] = self.params['seg_dict']
        num_in: int = self.params['num_in']
        export_outb: bool = self.params['export_outb']

        if num_in < 2 or num_in > 9:
            raise ValueError(f'num_in={num_in} has to be within 2 and 9.')

        sep_col = self.min_sep_col
        sep_col += sep_col & 1

        hm_layer = self.conn_layer + 1
        vm_layer = hm_layer + 1
        xm_layer = vm_layer + 1

        # pick hm_layer tracks
        pd_tidx = self.get_track_index(1, MOSWireType.DS, 'sig', 1)
        pg1_tid = self.get_track_id(1, MOSWireType.G, 'sig', -1)
        pg1_tidx = self.get_track_index(1, MOSWireType.G, 'sig', -1)
        pg0_tidx = self.get_track_index(1, MOSWireType.G, 'sig', -2)
        ng1_tidx = self.get_track_index(0, MOSWireType.G, 'sig', 1)
        ng0_tidx = self.get_track_index(0, MOSWireType.G, 'sig', 0)
        ng0_tid = self.get_track_id(0, MOSWireType.G, 'sig', 0)
        nd_tidx = self.get_track_index(0, MOSWireType.DS, 'sig', -2)
        sig_locs_inv = {'nin': ng0_tidx, 'nin0': ng0_tidx, 'nin1': ng1_tidx, 'nin2': pg0_tidx}
        sig_locs_nor = {'nin': pg1_tidx, 'nin0': pg1_tidx, 'nin1': pg0_tidx, 'nin2': ng1_tidx, 'nout': nd_tidx,
                        'pout': pd_tidx}

        # nand configuration
        nand_in_list = self._nand_in_list
        nor_in = len(nand_in_list)
        nand_params = dict(pinfo=pinfo, seg=seg_dict['nand'], vertical_out=False)
        nand_out_list = []
        nand_sch_list = []
        cur_col = 0
        in_idx = 0
        vdd_list, vss_list = [], []
        prev_out_vm_tidx = self.grid.coord_to_track(vm_layer, 0, RoundMode.NEAREST)
        prev_out_vm_tidx = self.tr_manager.get_next_track(vm_layer, prev_out_vm_tidx, 'sig', 'sig', up=-1)
        w_sig_vm = self.tr_manager.get_width(vm_layer, 'sig')

        for nand_idx, nand_in in enumerate(nand_in_list):
            # make master
            back_idx = nor_in - 1 - nand_idx
            nand_params['sig_locs'] = sig_locs_nor if (back_idx & 1) else sig_locs_inv
            if nand_in == 3:
                _master = self.new_template(NAND3Core, params=nand_params)
            else:  # nand_n == 2
                _master = self.new_template(NAND2Core, params=nand_params)

            # find placement based on nand width and also vm_layer wires
            out_vm_tidx = self.tr_manager.get_next_track(vm_layer, prev_out_vm_tidx, 'sig', 'sig', up=nand_in * 2 + 1)
            out_vm_tidx2 = self.grid.coord_to_track(vm_layer, self.sd_pitch * (cur_col + _master.num_cols),
                                                    RoundMode.NEAREST)
            if out_vm_tidx > out_vm_tidx2:
                _coord = self.grid.track_to_coord(vm_layer, out_vm_tidx)
                avail_col = -(- _coord // self.sd_pitch) - _master.num_cols
                offset = avail_col - cur_col
                cur_col += offset + (offset & 1)
                out_vm_tidx = self.grid.coord_to_track(vm_layer, self.sd_pitch * (cur_col + _master.num_cols),
                                                       RoundMode.NEAREST)
            else:
                out_vm_tidx = out_vm_tidx2
            _inst = self.add_tile(_master, 0, cur_col)
            nand_sch_list.append(_master.sch_params)

            # supplies
            vdd_list.append(_inst.get_pin('VDD'))
            vss_list.append(_inst.get_pin('VSS'))

            # nand inputs
            for _in_idx in range(nand_in):
                self.reexport(_inst.get_port(f'nin<{_in_idx}>'), net_name=f'in<{in_idx}>', hide=False)
                in_idx += 1

            # nand output
            nand_out_vm = self.connect_to_tracks([_inst.get_pin('pout'), _inst.get_pin('nout')],
                                                 TrackID(vm_layer, out_vm_tidx, w_sig_vm))
            nand_out_list.append(nand_out_vm)
            self.add_pin(f'nand_out{nand_idx}', nand_out_vm, hide=True)

            # setup for next instance
            cur_col += _master.num_cols + sep_col
            prev_out_vm_tidx = out_vm_tidx

        # nor configuration
        if nor_in == 3:
            nor_master = self.new_template(NOR3Core,
                                           params=dict(pinfo=pinfo, seg=seg_dict['nor'], vertical_out=False,
                                                       sig_locs=sig_locs_nor))
        elif nor_in == 2:
            nor_master = self.new_template(NOR2Core,
                                           params=dict(pinfo=pinfo, seg=seg_dict['nor'], vertical_out=False,
                                                       sig_locs=sig_locs_nor))
        else:
            nor_master = self.new_template(InvCore,
                                           params=dict(pinfo=pinfo, seg=seg_dict['inv'], vertical_out=False,
                                                       sig_locs=sig_locs_nor))
        # find placement based on nor width and also vm_layer wires
        out_vm_tidx = self.tr_manager.get_next_track(vm_layer, prev_out_vm_tidx, 'sig', 'sig', up=nor_in + 1)
        out_vm_tidx2 = self.grid.coord_to_track(vm_layer, self.sd_pitch * (cur_col + nor_master.num_cols),
                                                RoundMode.NEAREST)
        if out_vm_tidx > out_vm_tidx2:
            _coord = self.grid.track_to_coord(vm_layer, out_vm_tidx)
            avail_col = -(- _coord // self.sd_pitch) - nor_master.num_cols
            offset = avail_col - cur_col
            cur_col += offset + (offset & 1)
            out_vm_tidx = self.grid.coord_to_track(vm_layer, self.sd_pitch * (cur_col + nor_master.num_cols),
                                                   RoundMode.NEAREST)
        else:
            out_vm_tidx = out_vm_tidx2
        nor = self.add_tile(nor_master, 0, cur_col)
        cur_col += nor_master.num_cols
        vdd_list.append(nor.get_pin('VDD'))
        vss_list.append(nor.get_pin('VSS'))

        # nor output
        out_vm = self.connect_to_tracks([nor.get_pin('pout'), nor.get_pin('nout')],
                                        TrackID(vm_layer, out_vm_tidx, w_sig_vm))
        out_hm = self.connect_to_tracks(out_vm, ng0_tid, min_len_mode=MinLenMode.UPPER)

        # nor inputs: find xm_layer tracks
        vdd_xm_tidx = self.grid.coord_to_track(xm_layer, vdd_list[-1].bound_box.ym, RoundMode.NEAREST)
        vss_xm_tidx = self.grid.coord_to_track(xm_layer, vss_list[-1].bound_box.ym, RoundMode.NEAREST)
        xm_locs = self.tr_manager.spread_wires(xm_layer, ['sup'] + ['sig'] * nor_in + ['sup'], vss_xm_tidx,
                                               vdd_xm_tidx, ('sup', 'sig'))
        vm_locs = self.tr_manager.spread_wires(vm_layer, ['sig'] * (nor_in + 2), prev_out_vm_tidx, out_vm_tidx,
                                               ('sig', 'sig'))
        w_sig_xm = self.tr_manager.get_width(xm_layer, 'sig')
        for _idx in range(nor_in):
            _in_name = 'nin' if nor_in == 1 else f'nin<{_idx}>'
            _nor_in = self.connect_to_tracks(nor.get_pin(_in_name), TrackID(vm_layer, vm_locs[1 + _idx],
                                             w_sig_vm), min_len_mode=MinLenMode.MIDDLE)
            self.connect_to_tracks([_nor_in, nand_out_list[_idx]], TrackID(xm_layer, xm_locs[-2 - _idx], w_sig_xm))

        # output inverter
        if export_outb:
            cur_col += sep_col
            inv_master = self.new_template(InvCore,
                                           params=dict(pinfo=pinfo, seg=seg_dict['inv'],
                                                       sig_locs=sig_locs_inv))
            out_inv = self.add_tile(inv_master, 0, cur_col)
            cur_col += inv_master.num_cols
            inv_sch = inv_master.sch_params
            vdd_list.append(out_inv.get_pin('VDD'))
            vss_list.append(out_inv.get_pin('VSS'))

            out_hm = self.connect_wires([out_hm, out_inv.get_pin('nin')])[0]
            outb_hm = self.connect_to_tracks(out_inv.get_pin('out'), pg1_tid, min_len_mode=MinLenMode.UPPER)
            self.add_pin('outb', outb_hm)
        else:
            inv_sch = None
        self.add_pin('out', out_hm)

        self.set_mos_size()

        # supplies
        self.add_pin('VDD', self.connect_wires(vdd_list))
        self.add_pin('VSS', self.connect_wires(vss_list))

        self.sch_params = dict(
            nand_params_list=nand_sch_list,
            nor_params=nor_master.sch_params,
            inv_params=inv_sch,
            export_outb=export_outb,
        )


class AndComplexCol(MOSBase):
    def __init__(self, temp_db: TemplateDB, params: Param, **kwargs: Any) -> None:
        MOSBase.__init__(self, temp_db, params, **kwargs)
        num_in: int = params['num_in']
        self._nand_in_list = get_nand_in_list(num_in)

    @property
    def nand_in_list(self) -> Sequence[int]:
        return self._nand_in_list

    @classmethod
    def get_schematic_class(cls) -> Optional[Type[Module]]:
        return bag3_digital__and_complex

    @classmethod
    def get_params_info(cls) -> Mapping[str, str]:
        return dict(
            pinfo='The MOSBasePlaceInfo object.',
            seg_dict='Dictionary of segments of standard cell components',
            num_in='Number of inputs',
            export_outb='True to export outb; True by default',
        )

    @classmethod
    def get_default_param_values(cls) -> Mapping[str, Any]:
        return dict(export_outb=True)

    def draw_layout(self) -> None:
        pinfo = MOSBasePlaceInfo.make_place_info(self.grid, self.params['pinfo'])
        self.draw_base(pinfo)

        seg_dict: Mapping[str, int] = self.params['seg_dict']
        num_in: int = self.params['num_in']
        export_outb: bool = self.params['export_outb']

        if num_in < 2 or num_in > 9:
            raise ValueError(f'num_in={num_in} has to be within 2 and 9.')

        sep_col = self.min_sep_col
        sep_col += sep_col & 1

        hm_layer = self.conn_layer + 1
        vm_layer = hm_layer + 1

        # nand configuration
        nand_in_list = self._nand_in_list
        nor_in = len(nand_in_list)
        nand_params = dict(pinfo=pinfo, seg=seg_dict['nand'], vertical_out=False)
        nand_sch_list = []
        nand_master_list = []
        nand_ncols = 0
        num_vm = nor_in + 1  # number of vm_layer wires for nor
        # make masters
        for nand_idx, nand_in in enumerate(nand_in_list):
            if nand_in == 3:
                _master = self.new_template(NAND3Core, params=nand_params)
            else:  # nand_n == 2
                _master = self.new_template(NAND2Core, params=nand_params)
            nand_master_list.append(_master)
            nand_sch_list.append(_master.sch_params)
            nand_ncols = max(nand_ncols, _master.num_cols)
            num_vm = max(num_vm, nand_in + nand_idx + 1)  # number of vm_layer wires for nand in this row,
            # and nand output of previous row

        # nor configuration
        if nor_in == 3:
            nor_master = self.new_template(NOR3Core,
                                           params=dict(pinfo=pinfo, seg=seg_dict['nor'], vertical_out=False))
        elif nor_in == 2:
            nor_master = self.new_template(NOR2Core,
                                           params=dict(pinfo=pinfo, seg=seg_dict['nor'], vertical_out=False))
        else:
            nor_master = self.new_template(InvCore,
                                           params=dict(pinfo=pinfo, seg=seg_dict['inv'], vertical_out=False))
        nor_ncols = nor_master.num_cols

        # output inverter
        if export_outb:
            inv_master = self.new_template(InvCore, params=dict(pinfo=pinfo, seg=seg_dict['inv'], vertical_out=False))
            inv_ncols = inv_master.num_cols
            inv_sch = inv_master.sch_params
        else:
            inv_master = None
            inv_ncols = 0
            inv_sch = None

        # size
        logic_ncols = max(nand_ncols, nor_ncols, inv_ncols)
        num_vm_tr, vm_locs = self.tr_manager.place_wires(vm_layer, ['sig'] * num_vm)
        vm_ncols = self.grid.track_to_coord(vm_layer, num_vm_tr) // self.sd_pitch
        tot_ncols = max(logic_ncols, vm_ncols)

        # --- Placement --- #
        tile_idx = 0
        w_sig_vm = self.tr_manager.get_width(vm_layer, 'sig')
        nor_in_list = []
        in_idx = 0
        vdd_list, vss_list = [], []
        for _master in nand_master_list:
            _nand = self.add_tile(_master, tile_idx, nand_ncols, flip_lr=True)

            # output on vm_layer
            nor_in_list.append(self.connect_to_tracks([_nand.get_pin('pout'), _nand.get_pin('nout')],
                                                      TrackID(vm_layer, vm_locs[tile_idx], w_sig_vm)))
            
            # input on vm_layer
            nand_in = nand_in_list[tile_idx]
            for _in_idx in range(nand_in):
                vm_idx = -1 - _in_idx
                _in = self.connect_to_tracks(_nand.get_pin(f'nin<{_in_idx}>'),
                                             TrackID(vm_layer, vm_locs[vm_idx], w_sig_vm),
                                             min_len_mode=MinLenMode.MIDDLE)
                self.add_pin(f'in<{in_idx}>', _in)
                in_idx += 1

            # supplies
            vdd_list.append(_nand.get_pin('VDD'))
            vss_list.append(_nand.get_pin('VSS'))

            # setup for next iterationaaa
            tile_idx += 1

        nor = self.add_tile(nor_master, tile_idx, 0)
        # nor inputs
        if nor_in == 1:
            self.connect_to_track_wires(nor.get_pin('nin'), nor_in_list[0])
        else:
            for _idx, _nor_in in enumerate(nor_in_list):
                self.connect_to_track_wires(nor.get_pin(f'nin<{_idx}>'), nor_in_list[_idx])
        # nor output
        out_vm = self.connect_to_tracks([nor.get_pin('pout'), nor.get_pin('nout')],
                                        TrackID(vm_layer, vm_locs[nor_in], w_sig_vm))
        # supplies
        vdd_list.append(nor.get_pin('VDD'))
        vss_list.append(nor.get_pin('VSS'))
        tile_idx += 1

        if export_outb:
            inv_col = -(- max(nor_ncols, inv_ncols)) // 2 * 2
            inv = self.add_tile(inv_master, tile_idx, inv_col, flip_lr=True)
            # input
            out_vm = self.connect_to_track_wires(inv.get_pin('nin'), out_vm)
            # output
            outb_vm = self.connect_to_tracks([inv.get_pin('pout'), inv.get_pin('nout')],
                                             TrackID(vm_layer, vm_locs[nor_in - 1], w_sig_vm))
            self.add_pin('outb', outb_vm)
            # supplies
            vdd_list.append(inv.get_pin('VDD'))
            vss_list.append(inv.get_pin('VSS'))
            tile_idx += 1
        self.add_pin('out', out_vm)

        self.set_mos_size(tot_ncols, tile_idx)

        # supplies
        self.add_pin('VDD', self.connect_wires(vdd_list))
        self.add_pin('VSS', self.connect_wires(vss_list))

        self.sch_params = dict(
            nand_params_list=nand_sch_list,
            nor_params=nor_master.sch_params,
            inv_params=inv_sch,
            export_outb=export_outb,
        )


def get_nand_in_list(num_in: int) -> Sequence[int]:
    q, r = divmod(num_in, 3)
    if r == 0:
        return [3] * q
    elif r == 1:
        return [3] * (q - 1) + [2, 2]
    else:  # r == 2
        return [3] * q + [2]
