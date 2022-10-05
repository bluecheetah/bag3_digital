# BSD 3-Clause License
#
# Copyright (c) 2018, Regents of the University of California
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# * Redistributions of source code must retain the above copyright notice, this
#   list of conditions and the following disclaimer.
#
# * Redistributions in binary form must reproduce the above copyright notice,
#   this list of conditions and the following disclaimer in the documentation
#   and/or other materials provided with the distribution.
#
# * Neither the name of the copyright holder nor the names of its
#   contributors may be used to endorse or promote products derived from
#   this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

# -*- coding: utf-8 -*-

from typing import Mapping, Any, Optional, Dict

import pkg_resources
from pathlib import Path

from pybag.enum import TermType

from bag.design.module import Module
from bag.design.database import ModuleDB
from bag.util.immutable import Param


# noinspection PyPep8Naming
class bag3_digital__demux_1to2(Module):
    """Module for library bag3_digital cell demux_1to2.

    Fill in high level description here.
    """

    yaml_file = pkg_resources.resource_filename(__name__,
                                                str(Path('netlist_info',
                                                         'demux_1to2.yaml')))

    def __init__(self, database: ModuleDB, params: Param, **kwargs: Any) -> None:
        Module.__init__(self, self.yaml_file, database, params, **kwargs)

    @classmethod
    def get_params_info(cls) -> Mapping[str, str]:
        """Returns a dictionary from parameter names to descriptions.

        Returns
        -------
        param_info : Optional[Mapping[str, str]]
            dictionary from parameter names to descriptions.
        """
        return dict(
            dlatch_params='DLatch parameters',
            in_buf_params='Optional input data buffer parameters. If None, removed. Defaults to None.',
            clk_buf_params='Optional inverter chain parameters to buffer clk and generate clkb. If None, '
                           'clkb is an input pin. If 1 stage, the data latches use the input clk and generated '
                           'clkb. If > 1 stage, the data latches use buffered clk and clkb. Defaults to None.',
            use_ff='True to have flip flops on both outputs (resulting in 2 latches on one way and 3 latches on the '
                   'other). False to have 1 latch on one way and 2 latches on the other. Defaults to False.',
            is_big_endian='True for big endian, False for little endian. Defaults to False.',
            export_nets='True to export intermediate nets. Defaults to False',
        )

    def get_master_basename(self):
        basename = super().get_master_basename()
        pfx = 'ff' if self.params['use_ff'] else 'latch'
        return f'{basename}_{pfx}'

    @classmethod
    def get_default_param_values(cls) -> Mapping[str, Any]:
        return dict(in_buf_params=None, clk_buf_params=None, use_ff=False, is_big_endian=False, export_nets=False)

    def design(self, dlatch_params: Param, in_buf_params: Optional[Param], clk_buf_params: Optional[Param],
               use_ff: bool, is_big_endian: bool, export_nets: bool) -> None:
        """To be overridden by subclasses to design this module.

        This method should fill in values for all parameters in
        self.parameters.  To design instances of this module, you can
        call their design() method or any other ways you coded.

        To modify schematic structure, call:

        rename_pin()
        delete_instance()
        replace_instance_master()
        reconnect_instance_terminal()
        restore_instance()
        array_instance()
        """
        self.remove_instance('XNC')

        nets_to_export = set()

        if in_buf_params is None:
            self.remove_instance('XBUFIN')
            in_net = 'in'
        else:
            self.instances['XBUFIN'].design(**in_buf_params)
            in_net = 'in_buf'
            nets_to_export.add('in_buf')

        if clk_buf_params is None:
            self.remove_instance('XBUFCLK')
            self.add_pin('clkb', TermType.input)
            clk_net = 'clk'
            clkb_net = 'clkb'
        else:
            clk_buf_params = clk_buf_params.copy(append=dict(dual_output=True, export_pins=False))
            self.instances['XBUFCLK'].design(**clk_buf_params)
            nets_to_export.add('clkb_buf')
            clkb_net = 'clkb_buf'
            if len(clk_buf_params['inv_params']) > 1:  # clkb is buffered
                clk_net = 'clk_buf'
                nets_to_export.add('clk_buf')
            else:
                clk_net = 'clk'

        if is_big_endian:
            idx_early = 1
            idx_late = 0
        else:
            idx_early = 0
            idx_late = 1

        self.instances['XLEARLY<1:0>'].design(**dlatch_params)
        self.instances['XLLATE'].design(**dlatch_params)
        if use_ff:
            late_conns = self.get_cascaded_latch_conns(2, in_net, f'out<{idx_late}>', 'mid_late', clk_net, clkb_net)
            early_conns = self.get_cascaded_latch_conns(3, in_net, f'out<{idx_early}>', 'mid_early', clk_net, clkb_net)
            self.rename_instance('XLLATE', 'XLLATE<1:0>', late_conns.items())
            self.rename_instance('XLEARLY<1:0>', 'XLEARLY<2:0>', early_conns.items())
        else:
            late_conns = self.get_cascaded_latch_conns(1, in_net, f'out<{idx_late}>', 'mid_late', clk_net, clkb_net)
            early_conns = self.get_cascaded_latch_conns(2, in_net, f'out<{idx_early}>', 'mid_early', clk_net, clkb_net)
            self.reconnect_instance('XLLATE', late_conns.items())
            self.reconnect_instance('XLEARLY<1:0>', early_conns.items())

        if export_nets:
            for pin in nets_to_export:
                self.add_pin(pin, TermType.inout)

    @staticmethod
    def get_cascaded_latch_conns(num_latches: int, in_net: str, out_net: str, mid_net_base: str,
                                 clk_net: str, clkb_net: str) -> Dict[str, str]:
        if num_latches > 1:
            mid_net = mid_net_base + (f'<{num_latches - 2}:0>' if num_latches > 2 else '')
            in_conn = f'{mid_net},{in_net}'
            out_conn = f'{out_net},{mid_net}'
        else:
            in_conn = in_net
            out_conn = out_net
        clk_conn = ','.join([clkb_net if i & 1 else clk_net for i in range(num_latches)])
        clkb_conn = ','.join([clk_net if i & 1 else clkb_net for i in range(num_latches)])
        conns = {
            'in': in_conn,
            'out': out_conn,
            'clk': clk_conn,
            'clkb': clkb_conn,
            'VDD': 'VDD',
            'VSS': 'VSS',
        }
        return conns