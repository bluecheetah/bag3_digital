"""This module contains layout generators for complex AND gate with 2 - 9 inputs"""

from typing import Mapping, Any, Optional, Type, Sequence, List, Tuple

from pybag.enum import MinLenMode, RoundMode

from bag.util.immutable import Param
from bag.design.module import Module
from bag.layout.template import TemplateDB
from bag.layout.routing.base import TrackID, WireArray

from xbase.layout.enum import MOSWireType
from xbase.layout.mos.base import MOSBasePlaceInfo, MOSBase

from .gates import NAND2Core, NAND3Core, NOR2Core, NOR3Core, InvCore
from .logic_unit import LogicUnit

from ...schematic.and_complex import bag3_digital__and_complex


class AndComplexRow(MOSBase):
    """A complex AND for B2T decoding. Used for passgate mux row decoder"""
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
        sig_locs_inv = {'nin': ng0_tidx, 'nin0': ng0_tidx, 'nin1': ng1_tidx, 'nin2': pg0_tidx, 'nout': nd_tidx,
                        'pout': pd_tidx}
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
    """A complex AND for B2T decoding. Used for passgate mux column decoder"""
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


class AndComplexColTall(MOSBase):
    """A complex AND for B2T decoding. Used for passgate mux column decoder
    Based on AndDiffRow from BAG2
    """
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

    def get_layout_basename(self) -> str:
        return f"androw_diff{self.params['num_in']}_{self.params['seg_dict']['nand']}x"

    def draw_layout(self) -> None:
        pinfo = MOSBasePlaceInfo.make_place_info(self.grid, self.params['pinfo'])
        self.draw_base(pinfo)

        seg_dict: Mapping[str, int] = self.params['seg_dict']
        num_in: int = self.params['num_in']
        export_outb: bool = self.params['export_outb']
        
        # TODO: do we need to parametrize these at all?
        seg = 2
        sig_locs = {}
        
        out_vm = True

        if num_in < 2 or num_in > 9:
            raise ValueError(f'num_in={num_in} has to be within 2 and 9.')

        sep_col = self.min_sep_col
        sep_col += sep_col & 1

        # calculate the number of nand gates
        nand_nin_list = self._nand_in_list
        nor_in = num_nand = len(nand_nin_list)
        num_nor_unit = 1 if num_nand < 2 else num_nand
        num_unit = sum(nand_nin_list) + num_nor_unit
        if export_outb:
            num_unit += 1

        # compute track locations
        hm_layer = self.conn_layer + 1
        vm_layer = hm_layer + 1
        tr_manager = self.tr_manager
        tr_w_out_v = tr_manager.get_width(vm_layer, 'sig')

        # Create templates
        params = self.params.copy(append=dict(seg=seg), remove=seg_dict)
        unit_template = self.new_template(params=params, temp_cls=LogicUnit)

        # Size. Set either by logic or by wires 
        logic_ncols = unit_template.num_cols
        # Compute number of wires required
        num_nand_int = 2  # internal to nands, alternatings. Outputs are in nand_nor
        num_nand_nor = nor_in  # number of connects from nand to nor
        num_nor_int = nor_in  # internal to nand, plus the output wire
        num_vm = max(num_nand_int, num_nor_int) + num_nand_nor
        num_vm_tr, vm_locs = self.tr_manager.place_wires(vm_layer, ['sig'] * num_vm)
        vm_ncols = self.grid.track_to_coord(vm_layer, num_vm_tr) // self.sd_pitch
        tot_ncols = max(logic_ncols, vm_ncols)
        
        self.set_mos_size(tot_ncols)

        # ===== Placement =====
        # add instances
        unit_inst = []
        for idy in range(num_unit):
            unit_inst.append(self.add_tile(unit_template, idy, 0))

        # make NAND/NOR gates
        tile_idx = 0
        in_list, vss_list, vdd_list, mid_list = [], [], [], []

        # Make NANDS
        for cur_nin in nand_nin_list:
            nand_tmp = self._make_nand_row(cur_nin, sig_locs, tile_idx, unit_inst, vm_locs, vss_list, vdd_list)
            nand_in_warr, nand_out_warr = nand_tmp
            in_list += nand_in_warr
            mid_list += nand_out_warr
            tile_idx += cur_nin
            
        # Make NOR
        # Make "1-input nor" = inv
        if num_nand == 1:
            nor_tmp = self._make_inv_row(sig_locs, tile_idx, unit_inst, vm_locs, vss_list, vdd_list)
        else:
            nor_tmp = self._make_nor_row(num_nand, sig_locs, tile_idx, unit_inst, vm_locs, vss_list, vdd_list)
        nor_in_warr, nor_out_warr = nor_tmp
        tile_idx += num_nand

        # make outb inverter
        inv2_in_warr, inv2_out_warr = None, None
        if export_outb:
            inv_tmp = self._make_inv_row(sig_locs, tile_idx, unit_inst, vm_locs, vss_list, vdd_list)
            inv2_in_warr, inv2_out_warr = inv_tmp

        # ===== Routing =====
        # export input
        in_shift = get_in_shift(num_in)
        w_sig_vm = tr_manager.get_width(vm_layer, 'sig')
        for idy in range(num_in):
            pname = 'in<%d>' % idy
            vm_tidx = vm_locs[in_shift[idy]]
            _in = self.connect_to_tracks(in_list[idy], TrackID(vm_layer, vm_tidx, w_sig_vm),
                                         min_len_mode=MinLenMode.MIDDLE)
            self.add_pin(pname, _in)

        # connect mid wires
        idx_nand_nor_start = max(num_nand_int, num_nor_int)
        idx = 0
        for num_mid in range(num_nand):
            cur_nin = nand_nin_list[num_mid]
            mid_warr = mid_list[idx:cur_nin + 1 + idx]
            idx = cur_nin + 1 + idx
            mid_warr.append(nor_in_warr[num_mid])
            col_idx = idx_nand_nor_start + num_mid
            mid_tidy = vm_locs[col_idx]
            tid = TrackID(vm_layer, mid_tidy, width=tr_w_out_v)
            self.connect_to_tracks(mid_warr, tid)

        if export_outb:
            nor_out_warr.append(inv2_in_warr)

        # connect out wire
        out, outb = nor_out_warr, inv2_out_warr
        if out_vm:
            # Get the highest NOR wire, preallocated
            col_idx = num_nor_int - 1
            out_tidy = vm_locs[col_idx]
            tid = TrackID(vm_layer, out_tidy, width=tr_w_out_v)
            out_warrs = nor_out_warr
            if export_outb:
                out_warrs.append(inv2_in_warr)
            out = self.connect_to_tracks(out_warrs, tid)

            if export_outb:
                # There should be room to the left of the out
                col_idx = num_nor_int - 2
                mid_tidy = vm_locs[col_idx]
                tid = TrackID(vm_layer, mid_tidy, width=tr_w_out_v)
                outb = self.connect_to_tracks(inv2_out_warr, tid)

        # export output
        self.add_pin('out', out)
        if export_outb:
            self.add_pin('outb', outb)

        # connect/export VSS/VDD
        self.add_pin('VSS', vss_list, connect=True)
        self.add_pin('VDD', vdd_list, connect=True)

        # ===== Schematic Params =====
        ridx_n, ridx_p = 0, -1
        base_params = dict(
            lch=self.place_info.lch,
            w_p=self.place_info.get_row_place_info(ridx_p).row_info.width,
            w_n=self.place_info.get_row_place_info(ridx_n).row_info.width,
            th_n=self.place_info.get_row_place_info(ridx_n).row_info.threshold,
            th_p=self.place_info.get_row_place_info(ridx_p).row_info.threshold,
            stack_p=1,
            stack_n=1,
            )
        nand_sch_list = []
        for nand_in in self.nand_in_list:
            params = base_params.copy()
            params.update(dict(
                num_in=nand_in,
                seg_p=seg_dict['nand'],
                seg_n=seg_dict['nand'],
                shared_mid=True,
            ))
            nand_sch_list.append(params)
        nor_params = base_params.copy()
        nor_params.update(dict(
                num_in=nor_in,
                seg_p=seg_dict['nor'],
                seg_n=seg_dict['nor'],
                shared_mid=True,
            ))
        inv_params = base_params.copy()
        inv_params.update(dict(
                num_in=1,
                seg_p=seg_dict['inv'],
                seg_n=seg_dict['inv'],
            ))
        nor_sch = nor_params if nor_in > 1 else inv_params
        inv_sch = inv_params if export_outb else None
        self.sch_params = dict(
            nand_params_list=nand_sch_list,
            nor_params=nor_sch,
            inv_params=inv_sch,
            export_outb=export_outb,
        )

    """
    _make_nand_row, _make_nor_row, and _make_inv_row all have the same signature.
    Given some inputs, connect up the appropriate, save VDD + VSS, and return the inputs + outputs
    """
    def _make_nand_row(self, num_in: int, sig_locs: dict, tile_idx: int, unit_inst: list, 
                       vm_locs: list, vss_warr: list, vdd_warr: list) -> Tuple[List[WireArray], List[WireArray]]:
        # get sig locations
        gate_name = 'nand%d' % num_in
        in_tidx = []
        pout_tidx = []
        nmid_tidxs = []
        nmid_tidxd = []
        nmid_tidy = []
        for idx in range(num_in):
            name = '_in%d' % idx
            in_tidx.append(sig_locs.get(gate_name + name, None))
            name = '_pout%d' % idx
            pout_tidx.append(sig_locs.get(gate_name + name, None))
            name = '_nmidxs%d' % idx
            nmid_tidxs.append(sig_locs.get(gate_name + name, None))
            name = '_nmidxd%d' % idx
            nmid_tidxd.append(sig_locs.get(gate_name + name, None))
        for idy in range(num_in - 1):
            name = '_nmidy%d' % idy
            nmid_tidy.append(sig_locs.get(gate_name + name, None))
        nout_tidx = sig_locs.get(gate_name + 'nout', None)

        # get track locations
        nidx, pidx = 0, -1
        for idy in range(num_in):
            if in_tidx[idy] is None:
                in_tidx[idy] = self.get_track_index(nidx, MOSWireType.G, 'sig', wire_idx=-1, tile_idx=idy + tile_idx)
            if pout_tidx[idy] is None:
                pout_tidx[idy] = self.get_track_index(pidx, MOSWireType.DS, 'sig', wire_idx=0, tile_idx=idy + tile_idx)
            if nmid_tidxs[idy] is None:
                nmid_tidxs[idy] = self.get_track_index(nidx, MOSWireType.DS, 'sig', wire_idx=1, tile_idx=idy + tile_idx)
            if nmid_tidxd[idy] is None:
                nmid_tidxd[idy] = self.get_track_index(nidx, MOSWireType.DS, 'sig', wire_idx=0, tile_idx=idy + tile_idx)
        if nout_tidx is None:
            nout_tidx = self.get_track_index(nidx, MOSWireType.DS, 'sig', wire_idx=0, tile_idx=tile_idx + num_in-1)

        # compute track locations
        tr_manager = self.tr_manager
        hm_layer = self.conn_layer + 1
        vm_layer = hm_layer + 1
        tr_w_in = tr_manager.get_width(hm_layer, 'sig')
        tr_w_nmid_h = tr_manager.get_width(hm_layer, 'sig')
        tr_w_nmid_v = tr_manager.get_width(vm_layer, 'sig')
        tr_w_out_h = tr_manager.get_width(hm_layer, 'sig')

        # connect input, VDD/VSS, output
        in_warr, out_warr = [], []
        for idy in range(num_in):
            _ctidx = idy + tile_idx  # Current tile index
            # connect input
            tid = TrackID(hm_layer, in_tidx[idy], width=tr_w_in)
            in_warr.append(self.connect_to_tracks([unit_inst[_ctidx].get_pin('pg'), unit_inst[_ctidx].get_pin('ng')],
                                                  tid, min_len_mode=MinLenMode.MIDDLE))

            # connect VDD/VSS
            vss_warr.append(self.connect_to_tracks(unit_inst[_ctidx].get_pin('ns'),
                                                   unit_inst[_ctidx].get_pin('VSS').track_id)
                            if idy == 0 else unit_inst[idy + tile_idx].get_pin('VSS'))
            vdd_warr.append(self.connect_to_tracks(unit_inst[_ctidx].get_pin('ps'),
                                                   unit_inst[_ctidx].get_pin('VDD').track_id))

            # connect output
            tid = TrackID(hm_layer, pout_tidx[idy], width=tr_w_out_h)
            out_warr.append(self.connect_to_tracks(unit_inst[_ctidx].get_pin('pd'),
                                                   tid, min_len_mode=MinLenMode.MIDDLE))
            if idy == num_in - 1:
                tid = TrackID(hm_layer, nout_tidx, width=tr_w_out_h)
                out_warr.append(self.connect_to_tracks(unit_inst[_ctidx].get_pin('nd'),
                                                       tid, min_len_mode=MinLenMode.MIDDLE))

        # connect mid wires
        nmid_warr = []
        for idy in range(num_in):
            _ctidx = idy + tile_idx  # Current tile index
            tids = TrackID(hm_layer, nmid_tidxs[idy], width=tr_w_nmid_h)
            tidd = TrackID(hm_layer, nmid_tidxd[idy], width=tr_w_nmid_h)
            if idy == 0:
                nmid_warr.append(self.connect_to_tracks(unit_inst[_ctidx].get_pin('nd'), tidd,
                                                        min_len_mode=MinLenMode.MIDDLE))
            elif idy == num_in - 1:
                nmid_warr.append(self.connect_to_tracks(unit_inst[_ctidx].get_pin('ns'), tids,
                                                        min_len_mode=MinLenMode.MIDDLE))
            else:
                nmid_warr.append(self.connect_to_tracks(unit_inst[_ctidx].get_pin('ns'), tids,
                                                        min_len_mode=MinLenMode.MIDDLE))
                nmid_warr.append(self.connect_to_tracks(unit_inst[_ctidx].get_pin('nd'), tidd,
                                                        min_len_mode=MinLenMode.MIDDLE))

        unit_h = unit_inst[0].master.bound_box.h
        for idy in range(num_in - 1):
            warr1_yc = nmid_warr[idy * 2].bound_box.ym
            warr2_yc = nmid_warr[idy * 2 + 1].bound_box.ym
            col_idx = 0 if warr2_yc - warr1_yc > unit_h else 1
            if nmid_tidy[idy] is None:
                nmid_tidy[idy] = vm_locs[col_idx]
            tid = TrackID(vm_layer, nmid_tidy[idy], width=tr_w_nmid_v)
            self.connect_to_tracks(nmid_warr[idy * 2:idy * 2 + 2], tid)

        return in_warr, out_warr

    def _make_nor_row(self, num_in: int, sig_locs: dict, tile_idx: int, unit_inst: list, 
                      vm_locs: list, vss_warr: list, vdd_warr: list) -> Tuple[List[WireArray], List[WireArray]]:

        # get sig locations
        gate_name = 'nor%d' % num_in
        in_tidx = []
        nout_tidx = []
        pmid_tidxs = []
        pmid_tidxd = []
        pmid_tidy = []
        for idx in range(num_in):
            name = '_in%d' % idx
            in_tidx.append(sig_locs.get(gate_name + name, None))
            name = '_nout%d' % idx
            nout_tidx.append(sig_locs.get(gate_name + name, None))
            name = '_pmidxs%d' % idx
            pmid_tidxs.append(sig_locs.get(gate_name + name, None))
            name = '_pmidxd%d' % idx
            pmid_tidxd.append(sig_locs.get(gate_name + name, None))
        for idy in range(num_in - 1):
            name = '_pmidy%d' % idy
            pmid_tidy.append(sig_locs.get(gate_name + name, None))
        pout_tidx = sig_locs.get(gate_name + 'pout', None)

        # get track locations
        nidx, pidx = 0, -1
        for idy in range(num_in):
            _ctidx = idy + tile_idx  # Current tile index
            if in_tidx[idy] is None:
                in_tidx[idy] = self.get_track_index(nidx, MOSWireType.G, 'sig', wire_idx=-1, tile_idx=_ctidx)
            if nout_tidx[idy] is None:
                nout_tidx[idy] = self.get_track_index(nidx, MOSWireType.DS, 'sig',  wire_idx=0, tile_idx=_ctidx)
            if pmid_tidxs[idy] is None:
                pmid_tidxs[idy] = self.get_track_index(pidx, MOSWireType.DS, 'sig',  wire_idx=1, tile_idx=_ctidx)
            if pmid_tidxd[idy] is None:
                pmid_tidxd[idy] = self.get_track_index(pidx, MOSWireType.DS, 'sig',  wire_idx=0, tile_idx=_ctidx)
        if pout_tidx is None:
            pout_tidx = self.get_track_index(pidx, MOSWireType.DS, 'sig', wire_idx=0, tile_idx=tile_idx + num_in - 1)

        # compute track locations
        tr_manager = self.tr_manager
        hm_layer = self.conn_layer + 1
        vm_layer = hm_layer + 1
        tr_w_in = tr_manager.get_width(hm_layer, 'sig')
        tr_w_pmid_h = tr_manager.get_width(hm_layer, 'sig')
        tr_w_pmid_v = tr_manager.get_width(vm_layer, 'sig')
        tr_w_out_h = tr_manager.get_width(hm_layer, 'sig')

        # connect input, VDD/VSS, output
        in_warr, out_warr = [], []
        for idy in range(num_in):
            _ctidx = idy + tile_idx  # Current tile index
            # connect input
            tid = TrackID(hm_layer, in_tidx[idy], width=tr_w_in)
            in_warr.append(self.connect_to_tracks([unit_inst[_ctidx].get_pin('ng'), unit_inst[_ctidx].get_pin('pg')],
                                                  tid, min_len_mode=MinLenMode.MIDDLE))

            # connect VDD/VSS
            vdd_warr.append(self.connect_to_tracks(unit_inst[_ctidx].get_pin('ps'),
                                                   unit_inst[_ctidx].get_pin('VDD').track_id)
                            if idy == 0 else unit_inst[_ctidx].get_pin('VDD'))
            vss_warr.append(self.connect_to_tracks(unit_inst[_ctidx].get_pin('ns'),
                                                   unit_inst[_ctidx].get_pin('VSS').track_id))

            # connect output
            tid = TrackID(hm_layer, nout_tidx[idy], width=tr_w_out_h)
            out_warr.append(self.connect_to_tracks(unit_inst[_ctidx].get_pin('nd'), tid,
                                                   min_len_mode=MinLenMode.MIDDLE))
            if idy == num_in - 1:
                tid = TrackID(hm_layer, pout_tidx, width=tr_w_out_h)
                out_warr.append(self.connect_to_tracks(unit_inst[_ctidx].get_pin('pd'), tid,
                                                       min_len_mode=MinLenMode.MIDDLE))

        # connect mid wires
        pmid_warr = []
        for idy in range(num_in):
            _ctidx = idy + tile_idx  # Current tile_index
            tids = TrackID(hm_layer, pmid_tidxs[idy], width=tr_w_pmid_h)
            tidd = TrackID(hm_layer, pmid_tidxd[idy], width=tr_w_pmid_h)
            if idy == 0:
                pmid_warr.append(self.connect_to_tracks(unit_inst[_ctidx].get_pin('pd'),
                                                        tidd, min_len_mode=MinLenMode.MIDDLE))
            elif idy == num_in - 1:
                pmid_warr.append(self.connect_to_tracks(unit_inst[_ctidx].get_pin('ps'),
                                                        tids, min_len_mode=MinLenMode.MIDDLE))
            else:
                pmid_warr.append(self.connect_to_tracks(unit_inst[_ctidx].get_pin('ps'),
                                                        tids, min_len_mode=MinLenMode.MIDDLE))
                pmid_warr.append(self.connect_to_tracks(unit_inst[_ctidx].get_pin('pd'),
                                                        tidd, min_len_mode=MinLenMode.MIDDLE))

        for idy in range(num_in - 1):
            col_idx = 0 if idy % 2 == 0 else 1
            if pmid_tidy[idy] is None:
                pmid_tidy[idy] = vm_locs[col_idx]
            tid = TrackID(vm_layer, pmid_tidy[idy], width=tr_w_pmid_v)
            self.connect_to_tracks(pmid_warr[idy * 2:idy * 2 + 2], tid)

        return in_warr, out_warr

    def _make_inv_row(self, sig_locs: dict, tile_idx: int, unit_inst: list, 
                      vm_locs: list, vss_warr: list, vdd_warr: list) -> Tuple[WireArray, WireArray]:

        # get sig locations
        in_tidx = sig_locs.get('inv_in', None)
        pout_tidx = sig_locs.get('inv_pout', None)
        nout_tidx = sig_locs.get('inv_nout', None)

        # get track locations
        nidx, pidx = 0, -1
        if in_tidx is None:
            in_tidx = self.get_track_index(nidx, MOSWireType.G, 'sig', wire_idx=-1, tile_idx=tile_idx)

        if pout_tidx is None:
            pout_tidx = self.get_track_index(pidx, MOSWireType.DS, 'sig', wire_idx=0, tile_idx=tile_idx)
        if nout_tidx is None:
            nout_tidx = self.get_track_index(nidx, MOSWireType.DS, 'sig', wire_idx=0, tile_idx=tile_idx)

        # compute track locations
        tr_manager = self.tr_manager
        hm_layer = self.conn_layer + 1
        tr_w_in = tr_manager.get_width(hm_layer, 'in')
        tr_w_out_h = tr_manager.get_width(hm_layer, 'out')

        # connect input
        tid = TrackID(hm_layer, in_tidx, width=tr_w_in)
        in_warr = self.connect_to_tracks([unit_inst[tile_idx].get_pin('pg'),
                                          unit_inst[tile_idx].get_pin('ng')], tid, min_len_mode=MinLenMode.MIDDLE)

        # connect VDD/VSS
        vss_warr.append(self.connect_to_tracks(unit_inst[tile_idx].get_pin('ns'),
                                               unit_inst[tile_idx].get_pin('VSS').track_id))
        vdd_warr.append(self.connect_to_tracks(unit_inst[tile_idx].get_pin('ps'),
                                               unit_inst[tile_idx].get_pin('VDD').track_id))

        # connect output
        tid = TrackID(hm_layer, pout_tidx, width=tr_w_out_h)
        pout_warr = self.connect_to_tracks(unit_inst[tile_idx].get_pin('pd'), tid, min_len_mode=MinLenMode.MIDDLE)
        tid = TrackID(hm_layer, nout_tidx, width=tr_w_out_h)
        nout_warr = self.connect_to_tracks(unit_inst[tile_idx].get_pin('nd'), tid, min_len_mode=MinLenMode.MIDDLE)

        out_warr = self.connect_wires([pout_warr, nout_warr])

        return in_warr, out_warr


def get_nand_in_list(num_in: int) -> Sequence[int]:
    q, r = divmod(num_in, 3)
    if r == 0:
        return [3] * q
    elif r == 1:
        return [3] * (q - 1) + [2, 2]
    else:  # r == 2
        return [3] * q + [2]


def get_in_shift(num_in: int) -> Sequence[int]:
    nand_in_list = get_nand_in_list(num_in)
    ans = []
    for nand_num in nand_in_list:
        if nand_num == 2:
            ans.extend([1, 1])
        else:
            ans.extend([1, 1, 0])
    return ans
