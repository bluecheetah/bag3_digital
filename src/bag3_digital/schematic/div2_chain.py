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

from typing import Mapping, Any, Union, Sequence, Optional

import pkg_resources
from pathlib import Path

from pybag.enum import TermType

from bag.design.module import Module
from bag.design.database import ModuleDB
from bag.util.immutable import Param, ImmutableSortedDict


# noinspection PyPep8Naming
class bag3_digital__div2_chain(Module):
    """Module for library bag3_digital cell div2_chain.

    Fill in high level description here.
    """

    yaml_file = pkg_resources.resource_filename(__name__,
                                                str(Path('netlist_info',
                                                         'div2_chain.yaml')))

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
            num_stages='Number of stages.',
            div_params_list='List of divider parameters. If not a list, assumed to have the same parameter per stage',
            clk_div_buf_params_list='List of divided clock buffer parameters. If an entry is None, removed.'
                                    'If not a list, assumed to have same parameter per stage. Defaults to None.',
            inv_clk_div_list='List of booleans mapping whether each divider (after the first) should invert its input '
                             'clock. If a list, should have length num_stages - 1. If not a list, assumed to have the '
                             'same boolean per divider. Defaults to False.',
            clk_buf_params='Input clock buffer parameters. If None, removed. Defaults to None.',
            clk_gate_params='Clock gate parameters. If None, removed. Defaults to None.',
            output_clk_divb='True to output clk_divb nets. Defaults to True',
            export_nets='True to export intermediate nets. Defaults to False',
        )

    @classmethod
    def get_default_param_values(cls) -> Mapping[str, Any]:
        return dict(clk_div_buf_params_list=None, inv_clk_div_list=False, clk_buf_params=None, clk_gate_params=None,
                    output_clk_divb=True, export_nets=False)

    def design(self, num_stages: int, div_params_list: Union[Param, Sequence[Param]],
               clk_div_buf_params_list: Optional[Union[Param, Sequence[Param]]],
               inv_clk_div_list: Union[bool, Sequence[bool]], clk_buf_params: Optional[Param],
               clk_gate_params: Optional[Param], output_clk_divb: bool, export_nets: bool) -> None:
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
        nets_to_export = set()
        div_name_list = [f'XDIV{i}' for i in range(num_stages)]
        clk_div_buf_name_list = [f'XBUFDIV{i}' for i in range(num_stages)]
        if isinstance(div_params_list, ImmutableSortedDict):
            div_params_list = [div_params_list] * num_stages
        elif len(div_params_list) != num_stages:
            raise ValueError(f"div_params_list does not have length num_stages = {num_stages}")
        if clk_div_buf_params_list is None:
            clk_div_buf_params_list = [None] * num_stages
        elif isinstance(clk_div_buf_params_list, ImmutableSortedDict):
            clk_div_buf_params_list = [clk_div_buf_params_list] * num_stages
        elif len(clk_div_buf_params_list) != num_stages:
            raise ValueError(f"clk_div_buf_params_list does not have length num_stages = {num_stages}")
        if isinstance(inv_clk_div_list, bool):
            inv_clk_div_list = [inv_clk_div_list] * (num_stages - 1)
        elif len(inv_clk_div_list) != num_stages - 1:
            raise ValueError(f"inv_clk_div_list does not have length num_stages - 1 = {num_stages - 1}")
        self.array_instance('XDIV', div_name_list)
        self.array_instance('XBUFDIV', clk_div_buf_name_list)

        if clk_buf_params:
            clk_buf_params = clk_buf_params.copy(append=dict(dual_output=False))
            self.instances['XBUFCLK'].design(**clk_buf_params)
            if 'outb' in self.instances['XBUFCLK'].master.pins:
                clk_net_post_buf = 'clk_bufb'
            else:
                clk_net_post_buf = 'clk_buf'
            nets_to_export.add(clk_net_post_buf)
        else:
            self.remove_instance('XBUFCLK')
            clk_net_post_buf = 'clk'

        clk_gate_name = 'XCLKGATE'
        if clk_gate_params:
            clk_gate_inst = self.instances[clk_gate_name]
            clk_gate_inst.design(**clk_gate_params)
            self.reconnect_instance_terminal(clk_gate_name, 'clk', clk_net_post_buf)
            clk_net_post_gate = 'gclk'
            nets_to_export.add(clk_net_post_gate)

            conns = {}
            for pin, term_type in clk_gate_inst.master.pins.items():
                if not clk_gate_inst.get_connection(pin):
                    new_pin = f'clk_gate_{pin}'
                    conns[pin] = new_pin
                    self.add_pin(new_pin, term_type)
            self.reconnect_instance(clk_gate_name, conns.items())
        else:
            self.remove_instance(clk_gate_name)
            self.remove_pin('en')
            clk_net_post_gate = clk_net_post_buf

        self.reconnect_instance_terminal(div_name_list[0], 'clk', clk_net_post_gate)

        inv_clk_div_list = [None] + list(inv_clk_div_list)
        for i, (div_name, div_params, buf_name, buf_params, inv_clk_div) in \
                enumerate(zip(div_name_list, div_params_list, clk_div_buf_name_list, clk_div_buf_params_list,
                              inv_clk_div_list)):
            div_conns = {}
            clk_div_net = f'clk_div_{i}'
            clk_divb_net = f'clk_divb_{i}'
            if i > 0:  # handle clock inversion. First divider case should already be handled above.
                div_conns['clk'] = f'clk_divb_{i - 1}' if inv_clk_div else f'clk_div_{i - 1}'
            self.instances[div_name].design(**div_params)
            if buf_params:  # has buffer for divided clock
                buf_params = buf_params.copy(append=dict(dual_output=True))
                div_out_net = f'div_out_{i}'
                div_outb_net = f'div_outb_{i}'
                div_conns.update(dict(
                    clk_div=div_out_net,
                    clk_divb=div_outb_net
                ))
                self.instances[buf_name].design(**buf_params)
                self.reconnect_instance(buf_name, {'in': div_out_net, 'out': clk_div_net, 'outb': clk_divb_net}.items())
                nets_to_export.update({div_out_net, div_outb_net})
            else:  # no buffer for divided clock
                self.remove_instance(buf_name)
                div_conns['clk_div'] = clk_div_net
                div_conns['clk_divb'] = clk_divb_net
            self.reconnect_instance(div_name, div_conns.items())

        for i in range(num_stages):
            clk_div_net = f'clk_div_{i}'
            clk_divb_net = f'clk_divb_{i}'
            if output_clk_divb:
                if i == 0:
                    self.rename_pin('clk_divb', clk_divb_net)
                else:
                    self.add_pin(clk_divb_net, TermType.output)
            else:
                if i == 0:
                    self.remove_pin('clk_divb')
                nets_to_export.add(clk_divb_net)
                
            if i == 0:
                self.rename_pin('clk_div', clk_div_net)
            else:
                self.add_pin(clk_div_net, TermType.output)

        for net in nets_to_export:
            self.add_pin(net, TermType.inout)
