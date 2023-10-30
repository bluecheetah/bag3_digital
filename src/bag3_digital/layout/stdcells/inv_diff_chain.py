from cProfile import label
from typing import Any, Mapping, Optional, Type

from bag.util.immutable import Param
from bag.design.module import Module
from bag.layout.template import TemplateDB
from bag.layout.routing.base import TrackID

from xbase.layout.mos.base import MOSBasePlaceInfo, MOSBase, MOSWireType

from .inv_diff import InvDiffCore, CurrentStarvedInvDiffCore
from ...schematic.inv_diff_chain import bag3_digital__inv_diff_chain


class InvDiffChain(MOSBase):
    """Differential inverter cell chain using inverters"""
    def __init__(self, temp_db: TemplateDB, params: Param, **kwargs: Any) -> None:
        MOSBase.__init__(self, temp_db, params, **kwargs)

    @classmethod
    def get_schematic_class(cls) -> Optional[Type[Module]]:
        return bag3_digital__inv_diff_chain

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
            sig_locs='Signal track location dictionary.',
            length='Length of the chain',
            export_nodes='True to label nodes; False by default.',
            vertical_in='True to have inputs on vertical layer; False by default',
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
            sep_vert_in=False,
            sep_vert_out=False,
            vertical_in=False,
            length=1,
            export_nodes=False,
        )

    def draw_layout(self) -> None:
        pinfo = MOSBasePlaceInfo.make_place_info(self.grid, self.params['pinfo'])
        self.draw_base(pinfo)

        w_p: int = self.params['w_p']
        w_n: int = self.params['w_n']
        ridx_p: int = self.params['ridx_p']
        ridx_n: int = self.params['ridx_n']
        # sig_locs: Optional[Mapping[str, float]] = self.params['sig_locs']
        vertical_in: bool = self.params['vertical_in']
        sep_vert_in: bool = self.params['sep_vert_in']
        sep_vert_in = sep_vert_in and vertical_in
        seg_kp: int = self.params['seg_kp']
        seg_drv: int = self.params['seg_drv']
        length: int = self.params['length']
        export_nodes: bool = self.params['export_nodes']

        # --- make masters --- #
        # Inverter params
        inv_diff_params = dict(pinfo=pinfo,
                               seg_kp=seg_kp,
                               seg_drv=seg_drv,
                               w_p=w_p,
                               w_n=w_n,
                               ridx_p=ridx_p,
                               ridx_n=ridx_n,
                               vertical_in=False,
                               sep_vert_in=False,
                               sep_vert_out=False,
                               )
        inv_diff_master = self.new_template(InvDiffCore, params=inv_diff_params)

        # --- Placement --- #
        blk_sp = self.min_sep_col
        cur_col = blk_sp if sep_vert_in else 0
        drv_size = inv_diff_master.num_cols
        # Place inverters
        drivers = []
        for _ in range(length):
            drivers.append(self.add_tile(inv_diff_master,0, cur_col))
            cur_col += drv_size + blk_sp
        self.set_mos_size(cur_col)

        # --- Routing --- #
        # supplies
        vss_list, vdd_list = [], []
        for inst in drivers:
            vss_list.extend(inst.get_all_port_pins('VSS'))
            vdd_list.extend(inst.get_all_port_pins('VDD'))
        self.add_pin('VDD', self.connect_wires(vdd_list)[0])
        self.add_pin('VSS', self.connect_wires(vss_list)[0])

        # connect chain
        for idx in range(1, length):
            in_pin = drivers[idx].get_pin('in')
            inb_pin = drivers[idx].get_pin('inb')
            out_pin = drivers[idx-1].get_pin('out')
            outb_pin = drivers[idx-1].get_pin('outb')
            node = self.connect_wires([in_pin, out_pin])
            node_b = self.connect_wires([inb_pin, outb_pin])
            if export_nodes:
                self.add_pin(f'mid<{idx-1}>', node)
                self.add_pin(f'midb<{idx-1}>', node_b)

        # add input and output pins
        self.reexport(drivers[0].get_port('in'))
        self.reexport(drivers[0].get_port('inb'))
        self.reexport(drivers[-1].get_port('out'))
        self.reexport(drivers[-1].get_port('outb'))

        # get schematic parameters
        self.sch_params = dict(
            inv_diff=inv_diff_master.sch_params,
            length=length,
            export_nodes=export_nodes,
        )


class CurrentStarvedInvDiffChain(MOSBase):
    """Differential inverter cell chain using current-starved inverters"""
    def __init__(self, temp_db: TemplateDB, params: Param, **kwargs: Any) -> None:
        MOSBase.__init__(self, temp_db, params, **kwargs)

    @classmethod
    def get_schematic_class(cls) -> Optional[Type[Module]]:
        return bag3_digital__inv_diff_chain

    @classmethod
    def get_params_info(cls) -> Mapping[str, str]:
        return dict(
            pinfo='The MOSBasePlaceInfo object.',
            seg_drv='number of segments of inverter.',
            seg_mir='number of segments of mirror.',
            seg_kp='number of segments of keeper.',
            mir_align='mirror alignment. -1 for left, 1 for right.',
            mirror_ratio='ratio of current reference device to current mirrors. Only used if common_mir is True.',
            w_p='pmos width.',
            w_n='nmos width.',
            ridx_p='pmos row index.',
            ridx_n='nmos row index.',
            ridx_mir='nmos mirror row index.',
            sig_locs='Signal track location dictionary.',
            length='Length of the chain',
            export_nodes='True to label nodes; False by default.',
            vertical_in='True to have inputs on vertical layer; False by default',
            sep_vert_in='True to use separate vertical tracks for in and inb; False by default',
            sep_vert_out='True to use separate vertical tracks for out and outb; False by default',
            common_mir='True to draw common mirror; True by default',
            ptap_tile_idx='Ptap tile index.',
            ntap_tile_idx='Ntap tile index.',
            inv_tile_idx='Inverter tile index.',
        )

    @classmethod
    def get_default_param_values(cls) -> Mapping[str, Any]:
        return dict(
            w_p=0,
            w_n=0,
            ridx_p=-1,
            ridx_n=1,
            ridx_mir=0,
            mir_align=-1,
            mirror_ratio=1,
            sig_locs=None,
            sep_vert_in=False,
            sep_vert_out=False,
            vertical_in=False,
            length=1,
            export_nodes=False,
            common_mir=True,
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
        seg_kp: int = self.params['seg_kp']
        seg_drv: int = self.params['seg_drv']
        seg_mir: int = self.params['seg_mir']
        length: int = self.params['length']
        export_nodes: bool = self.params['export_nodes']

        common_mir: bool = self.params['common_mir']
        mir_align: int = self.params['mir_align']
        mirror_ratio: int = self.params['mirror_ratio']

        ptap_tile_idx: list[int] = self.params['ptap_tile_idx']
        ntap_tile_idx: int = self.params['ntap_tile_idx']
        inv_tile_idx: list[int] = self.params['inv_tile_idx']

        tr_manager = self.tr_manager

        # --- make masters --- #
        # Inverter params
        inv_diff_params = dict(pinfo=pinfo,
                               seg_kp=seg_kp,
                               seg_drv=seg_drv,
                               seg_mir=seg_mir,
                               draw_mir=not common_mir,
                               ridx_n=ridx_n, ridx_p=ridx_p, ridx_mir=ridx_mir,
                               )
        inv_diff_master = self.new_template(CurrentStarvedInvDiffCore, params=inv_diff_params)

        # --- Placement --- #
        blk_sp = self.min_sep_col
        cur_col = blk_sp if sep_vert_in else 0
        drv_size = inv_diff_master.num_cols
        # Place inverters
        drivers = []
        for _ in range(length):
            drivers.append(self.add_tile(inv_diff_master,0, cur_col))
            cur_col += drv_size + blk_sp
        total_col = cur_col - blk_sp
        self.set_mos_size(total_col)

        # --- Routing --- #
        hm_layer = self.conn_layer + 1
        vm_layer = hm_layer + 1

        # supplies
        vss_list, vdd_list = [], []
        vss_bot_taps_list, vss_top_taps_list = [], []
        for inst in drivers:
            vss_list.extend(inst.get_all_port_pins('VSS'))
            vdd_list.extend(inst.get_all_port_pins('VDD'))
            vss_bot_taps_list.extend(inst.get_all_port_pins('VSS_bot_taps'))
            vss_top_taps_list.extend(inst.get_all_port_pins('VSS_top_taps'))


        vdd_warr = self.connect_wires(vdd_list)
        vss_warrs = self.connect_wires(vss_list)
        self.add_pin('VDD', vdd_warr)
        self.add_pin('VSS', vss_warrs)


        # connect chain
        for idx in range(1, length):
            in_pin = drivers[idx].get_pin('in')
            inb_pin = drivers[idx].get_pin('inb')
            out_pin = drivers[idx-1].get_pin('out')
            outb_pin = drivers[idx-1].get_pin('outb')
            mid_port = drivers[idx-1].get_port('mid')
            midb_port = drivers[idx-1].get_port('midb')
            node = self.connect_wires([in_pin, out_pin])
            node_b = self.connect_wires([inb_pin, outb_pin])
            self.reexport(mid_port, net_name=f'mid<{idx-1}>', show=export_nodes)
            self.reexport(midb_port, net_name=f'midb<{idx-1}>', show=export_nodes)
        mid_port = drivers[-1].get_port('mid')
        midb_port = drivers[-1].get_port('midb')
        self.reexport(mid_port, net_name=f'mid<{length-1}>', show=export_nodes)
        self.reexport(midb_port, net_name=f'midb<{length-1}>', show=export_nodes)

        # add input and output pins
        self.reexport(drivers[0].get_port('in'), net_name='in', show=True)
        self.reexport(drivers[0].get_port('inb'), net_name='inb', show=True)
        self.reexport(drivers[-1].get_port('out'), net_name='out', show=True)
        self.reexport(drivers[-1].get_port('outb'), net_name='outb', show=True)



        # re-export ref_v pins
        if not common_mir:
            for stage, driver in enumerate(drivers):
                self.reexport(driver.get_port('ref_v_bot'), net_name=f'ref_v_bot<{stage}>', show=False)
                self.reexport(driver.get_port('ref_v_top'), net_name=f'ref_v_top<{stage}>', show=False)
        else:   # We'll need to draw the current mirror here
            # Get all the VSS_int connections for the drivers
            vss_int_bot_list = [driver.get_pin('VSS_int_bot') for driver in drivers]
            vss_int_top_list = [driver.get_pin('VSS_int_top') for driver in drivers]

            vss_mid_bot_tid = self.get_track_id(ridx_mir, MOSWireType.G, wire_name='sup',
                                                tile_idx=inv_tile_idx[0], wire_idx=-1)
            vss_mid_top_tid = self.get_track_id(ridx_mir, MOSWireType.G, wire_name='sup',
                                                tile_idx=inv_tile_idx[1], wire_idx=-1)

            # draw intermediate rails
            vss_int_bot = self.connect_to_tracks(vss_int_bot_list, vss_mid_bot_tid)
            vss_int_top = self.connect_to_tracks(vss_int_top_list, vss_mid_top_tid)

            self.add_pin('VSS_int_bot', vss_int_bot, hide=True)
            self.add_pin('VSS_int_top', vss_int_top, hide=True)

            # place current mirror
            col_mir = 0 if mir_align == -1 else total_col
            mir_bot = self.add_mos(0, col_mir, seg_mir * length,
                                   tile_idx=inv_tile_idx[0], flip_lr=mir_align == 1)
            mir_top = self.add_mos(0, col_mir, seg_mir * length,
                                   tile_idx=inv_tile_idx[1], flip_lr=mir_align == 1)
            col_ref = seg_mir * length + blk_sp if mir_align == -1 else (total_col - seg_mir * length - blk_sp)
            ref_seg = seg_mir * length / mirror_ratio
            if ref_seg % 1:
                raise ValueError(f'Mirror width {seg_mir} does not support current mirror ratio of {mirror_ratio}')
            ref_bot = self.add_mos(0, col_ref, int(ref_seg),
                                   tile_idx=inv_tile_idx[0], flip_lr=mir_align == 1)
            ref_top = self.add_mos(0, col_ref, int(ref_seg),
                                   tile_idx=inv_tile_idx[1], flip_lr=mir_align == 1)

            # make stubs for mirror drains
            mir_bot_d_tid = self.get_track_id(ridx_mir, MOSWireType.DS, 'sig', wire_idx=0, tile_idx=inv_tile_idx[0])
            mir_top_d_tid = self.get_track_id(ridx_mir, MOSWireType.DS, 'sig', wire_idx=0, tile_idx=inv_tile_idx[1])
            mir_bot_d_tie = self.connect_to_tracks(mir_bot.d, mir_bot_d_tid)
            mir_top_d_tie = self.connect_to_tracks(mir_top.d, mir_top_d_tid)

            # make vm connections to the intermediate rail
            mir_bot_d_vm = self.connect_via_stack(tr_manager, mir_bot_d_tie, vm_layer, w_type='sup')
            mir_top_d_vm = self.connect_via_stack(tr_manager, mir_top_d_tie, vm_layer, w_type='sup')

            self.connect_to_track_wires(vss_int_bot, mir_bot_d_vm)
            self.connect_to_track_wires(vss_int_top, mir_top_d_vm)

            # connect all current mirrors to VSS
            vss_bot_taps_list.extend([mir_bot.s, ref_bot.s])
            vss_top_taps_list.extend([mir_top.s, ref_top.s])
            self.connect_wires(vss_bot_taps_list)
            self.connect_wires(vss_top_taps_list)

            # connect gate connection
            bot_ref_v_tid = self.get_track_id(ridx_mir, MOSWireType.G, wire_name='sig', wire_idx=0,
                                              tile_idx=inv_tile_idx[0])
            bot_ref_v = self.connect_to_tracks([mir_bot.g, ref_bot.g, ref_bot.d], bot_ref_v_tid)
            self.add_pin('i_ref_bot', bot_ref_v, show=True)
            top_ref_v_tid = self.get_track_id(ridx_mir, MOSWireType.G, wire_name='sig', wire_idx=0,
                                              tile_idx=inv_tile_idx[1])
            top_ref_v = self.connect_to_tracks([mir_top.g, ref_top.g, ref_top.d], top_ref_v_tid)
            self.add_pin('i_ref_top', top_ref_v, show=True)

        # get schematic parameters
        self.sch_params = dict(
            inv_diff=inv_diff_master.sch_params,
            length=length,
            export_nodes=export_nodes,
        )
