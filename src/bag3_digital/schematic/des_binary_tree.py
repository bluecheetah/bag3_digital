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

from typing import Mapping, Any, Union, Optional, Sequence

import pkg_resources
from pathlib import Path

from pybag.enum import TermType

from bag.design.module import Module
from bag.design.database import ModuleDB
from bag.util.immutable import Param


# noinspection PyPep8Naming
class bag3_digital__des_binary_tree(Module):
    """Module for library bag3_digital cell des_binary_tree.

    Fill in high level description here.
    """

    yaml_file = pkg_resources.resource_filename(__name__,
                                                str(Path('netlist_info',
                                                         'des_binary_tree.yaml')))

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
            num_stages='Number of stages. Deserialization ratio is 2^num_stages',
            demux_params='Demux 1:2 parameters',
            use_ff_list='List of booleans mapping whether each demux stage should have flip flops on both outputs '
                        '(refer to Demux1To2 for more info). If a boolean is specified,'
                        'all stages will be set to this boolean. Defaults to False.',
            div_chain_params='Divide-by-2 divider chain parameters. If None, no divider chain is instantiated and '
                             'required clocks are added as input pins',
            din_buf_params='Input data buffer parameters. If None, removed. Defaults to None.',
            is_big_endian='True for big endian, False for little endian. Defaults to False.',
            export_nets='True to export intermediate nets. Defaults to False',
        )

    @classmethod
    def get_default_param_values(cls) -> Mapping[str, Any]:
        return dict(use_ff_list=False, div_chain_params=None, din_buf_params=None, is_big_endian=False,
                    export_nets=False)

    @property
    def ratio(self) -> int:
        return 1 << self.params['num_stages']

    @property
    def has_div(self) -> bool:
        return self.params['div_chain_params'] is not None

    def get_master_basename(self) -> str:
        return f'des_binary_tree_1to{self.ratio}'

    def design(self, num_stages: int, demux_params: Param, use_ff_list: Union[bool, Sequence[bool]],
               div_chain_params: Optional[Param], din_buf_params: Optional[Param], is_big_endian: bool,
               export_nets: bool) -> None:
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
        if isinstance(use_ff_list, bool):
            use_ff_list = [use_ff_list for _ in range(num_stages)]
        elif len(use_ff_list) != num_stages:
            raise ValueError(f"use_ff_list = {use_ff_list} must have length num_stages = {num_stages}")

        demux_name = 'XDEMUX'
        demux_params = demux_params.copy(append=dict(is_big_endian=is_big_endian, use_ff=use_ff_list[0]))
        self.instances[demux_name].design(**demux_params)

        nets_to_export = set()

        if din_buf_params is None:
            self.remove_instance('XBUFDIN')
            din_net = 'din'
        else:
            self.instances['XBUFDIN'].design(**din_buf_params)
            din_net = 'din_buf'
            nets_to_export.add('din_buf')

        div_chain_b_internal = self.instances[demux_name].master.pins.get('clkb', TermType.inout) == TermType.inout
        div_chain_name = 'XDIVCHAIN'
        if div_chain_params is None:  # remove div chain, add clk_div ports, remove clk and rst ports
            self.remove_instance(div_chain_name)
            self.remove_pin('clk')
            self.remove_pin('rst')
            self.remove_pin('en')
            self.remove_pin('clk_out')
            self.remove_instance('XTHRU')
            for i in range(num_stages):
                self.add_pin(f'clk_div_{i}', TermType.input)
            if not div_chain_b_internal:
                for i in range(num_stages):
                    self.add_pin(f'clk_divb_{i}', TermType.input)
        else:
            div_chain_inst = self.instances[div_chain_name]
            div_chain_params = div_chain_params.copy(append=dict(num_stages=num_stages))
            div_chain_inst.design(**div_chain_params)
            for i in range(num_stages):
                nets_to_export.add(f'clk_div_{i}')

            self.reconnect_instance_terminal('XTHRU', 'src', f'clk_div_{num_stages - 1}')

            div_chain_pins = div_chain_inst.master.pins
            for pin in div_chain_pins:
                if not div_chain_inst.get_connection(pin):
                    self.reconnect_instance_terminal(div_chain_name, pin, pin)
                    if not pin.startswith('clk_div'):
                        self.add_pin(pin, TermType.inout)

            if 'en' not in div_chain_pins:
                self.remove_pin('en')

        demux_name_list = []
        demux_term_list = []
        inst_change_list = []
        has_clk_buf_pin = 'clk_buf' in self.instances[demux_name].master.pins
        has_clkb_buf_pin = 'clkb_buf' in self.instances[demux_name].master.pins
        for stg_idx, use_ff in enumerate(use_ff_list):
            num_blocks = 1 << stg_idx
            num_bits = 2 * num_blocks
            is_first_stg = stg_idx == 0
            is_last_stg = stg_idx == num_stages - 1
            if not is_last_stg:
                nets_to_export.add(f'dmid_{stg_idx}<{num_bits - 1}:0>')
            for block_idx in range(num_blocks):
                block_name = f'{demux_name}_{stg_idx}_{block_idx}'
                out_base = 'dout' if is_last_stg else f'dmid_{stg_idx}'
                conns = {
                    'in': din_net if is_first_stg else f'dmid_{stg_idx - 1}<{block_idx}>',
                    'out<1:0>': f'{out_base}<{block_idx + num_blocks}>,{out_base}<{block_idx}>',
                    'clk': f'clk_div_{stg_idx}',
                    'clkb': f'clk_divb_{stg_idx}' + (f'_{block_idx}' if div_chain_b_internal else ''),
                }
                if has_clk_buf_pin:
                    net = f'clk_div_buf_{stg_idx}_{block_idx}'
                    conns['clk_buf'] = net
                    self.add_pin(net, TermType.inout)
                if has_clkb_buf_pin:
                    net = f'clk_divb_buf_{stg_idx}_{block_idx}'
                    conns['clkb_buf'] = net
                    self.add_pin(net, TermType.inout)
                demux_name_list.append(block_name)
                demux_term_list.append(conns)
                if use_ff != use_ff_list[0]:
                    inst_change_list.append(block_name)
        self.array_instance(demux_name, demux_name_list, demux_term_list)
        if inst_change_list:
            demux_params_other = demux_params.copy(append=dict(use_ff=not demux_params['use_ff']))
            for name in inst_change_list:
                self.instances[name].design(**demux_params_other)

        if self.ratio != 2:
            self.rename_pin('dout<1:0>', f'dout<{self.ratio - 1}:0>')

        if export_nets:
            for pin in nets_to_export:
                self.add_pin(pin, TermType.inout)
