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

from typing import Mapping, Any, Optional, List

import pkg_resources
from pathlib import Path

from pybag.enum import TermType

from bag.design.module import Module
from bag.design.database import ModuleDB
from bag.util.immutable import Param

from bag3_liberty.util import parse_cdba_name


# noinspection PyPep8Naming
class bag3_digital__des_array_binary_tree(Module):
    """Module for library bag3_digital cell des_array_binary_tree.

    Fill in high level description here.
    """

    yaml_file = pkg_resources.resource_filename(__name__,
                                                str(Path('netlist_info',
                                                         'des_array_binary_tree.yaml')))

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
            in_width='Input word width',
            narr='Number of arrayed words',
            unit_params='Unit deserializer parameters',
            ndum='Number of dummy units. Defaults to 0',
            div_chain_params='Divide-by-2 divider chain parameters. If None, no divider chain is instantiated and '
                             'required clocks are added as input pins',
            export_nets='True to export intermediate nets. Defaults to False',
            clk_out_metal_short_params='Resistor metal short parameters for clk_out. If not provided, clk_out is '
                                       'shorted to the last divided clock output via cds_thru. Only valid if a divider '
                                       'chain is instantiated.',
        )

    @classmethod
    def get_default_param_values(cls) -> Mapping[str, Any]:
        return dict(in_width=1, narr=1, ndum=0, div_chain_params=None, export_nets=False,
                    clk_out_metal_short_params=None)

    @property
    def num_stages(self) -> int:
        return self.params['unit_params']['num_stages']

    @property
    def ratio(self) -> int:
        return 1 << self.num_stages

    @property
    def narr(self):
        return self.params['narr']

    @property
    def in_width(self):
        return self.params['in_width']

    @property
    def out_width(self):
        return self.in_width * self.ratio

    @property
    def has_div(self) -> bool:
        return self.params['div_chain_params'] is not None

    def _get_arrayed_port(self, port_base: str, word_width: int) -> List[str]:
        if word_width == 1:
            return [f'{port_base}_{idx}' for idx in range(self.narr)]
        else:
            return [f'{port_base}_{idx}<{word_width - 1}:0>' for idx in range(self.narr)]

    def design(self, in_width: int, narr: int, unit_params: Param, ndum: int, div_chain_params: Optional[Param],
               export_nets: bool, clk_out_metal_short_params: Optional[Param]) -> None:
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
        num_stages = self.num_stages

        unit_name = 'XUNIT'
        unit_params = unit_params.copy(append=dict(div_chain_params=None))
        self.instances[unit_name].design(**unit_params)

        self.reconnect_instance(unit_name, {f'clk_div_{i}': f'clk_div_{i}' for i in range(num_stages)}.items())
        nc_unit_pins = [pin for pin in self.instances[unit_name].master.pins
                        if not self.instances[unit_name].get_connection(pin)]

        nets_to_export = set()

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
            if self.instances[unit_name].master.pins.get('clk_divb_0', TermType.inout) == TermType.input:
                for i in range(num_stages):
                    self.add_pin(f'clk_divb_{i}', TermType.input)
        else:
            div_chain_inst = self.instances[div_chain_name]
            div_chain_params = div_chain_params.copy(append=dict(num_stages=num_stages))
            div_chain_inst.design(**div_chain_params)
            for i in range(num_stages):
                nets_to_export.add(f'clk_div_{i}')
                nets_to_export.add(f'clk_divb_{i}')

            last_clk_div = f'clk_div_{num_stages - 1}'

            if clk_out_metal_short_params:
                self.replace_instance_master('XTHRU', 'xbase', 'metal_short')
                self.instances['XTHRU'].design(**clk_out_metal_short_params)
                self.reconnect_instance('XTHRU', dict(PLUS=last_clk_div, MINUS='clk_out').items())
            else:
                self.reconnect_instance_terminal('XTHRU', 'src', last_clk_div)

            div_chain_pins = div_chain_inst.master.pins
            for pin in div_chain_pins:
                if not div_chain_inst.get_connection(pin):
                    self.reconnect_instance_terminal(div_chain_name, pin, pin)
                    if not pin.startswith('clk_div'):
                        self.add_pin(pin, TermType.inout)

            if 'en' not in div_chain_pins:
                self.remove_pin('en')

        ratio = self.ratio
        out_width = in_width * ratio
        in_pins = self._get_arrayed_port('din', in_width)
        out_pins = self._get_arrayed_port('dout', out_width)

        unit_name_list = []
        unit_term_list = []
        if ndum:
            # Add dummy
            unit_name_list.append(f'{unit_name}DUM<{ndum - 1}:0>')
            unit_conns = {
                'din': 'VSS',
                f'dout<{ratio - 1}:0>': ','.join([f'nc_dum_dout_{i}<{ratio - 1}:0>' for i in range(ndum - 1, -1, -1)])
            }
            unit_conns.update({f'clk_div_{i}': 'VSS' for i in range(num_stages)})
            for pin in nc_unit_pins:
                if pin in unit_conns:
                    continue
                pin_base, pin_range = parse_cdba_name(pin)
                new_pin_base = f'nc_dum_{pin_base}'
                if pin_range is None:
                    new_pin_vec = [f'nc_dum_{new_pin_base}_{i}' for i in range(ndum - 1, -1, -1)]
                else:
                    new_pin_vec = [f'nc_dum_{new_pin_base}_{i}<{pin_range.start}:{pin_range.stop}>'
                                   for i in range(ndum - 1, -1, -1)]
                unit_conns[pin] = ','.join(new_pin_vec)
            unit_term_list.append(unit_conns)
        for arr_idx in range(narr):
            for bit_idx in range(in_width):
                sfx = f'_{arr_idx}_{bit_idx}'
                unit_name_list.append(unit_name + sfx)
                if in_width > 1:
                    unit_conns = {
                        'din': f'din_{arr_idx}<{bit_idx}>',
                        f'dout<{ratio - 1}:0>': ','.join([f'dout_{arr_idx}<{in_width * i + bit_idx}>'
                                                          for i in range(ratio - 1, -1, -1)])
                    }
                else:
                    unit_conns = {
                        'din': f'din_{arr_idx}',
                        f'dout<{ratio - 1}:0>': f'dout_{arr_idx}<{ratio - 1}:0>'
                    }
                for pin in nc_unit_pins:
                    if pin in unit_conns:
                        continue
                    pin_base, pin_range = parse_cdba_name(pin)
                    new_pin_base = pin_base + sfx
                    new_pin = new_pin_base if pin_range is None else \
                        new_pin_base + f'<{pin_range.start}:{pin_range.stop}>'
                    unit_conns[pin] = new_pin
                    self.add_pin(new_pin, TermType.inout)
                unit_term_list.append(unit_conns)
        self.array_instance(unit_name, unit_name_list, unit_term_list)

        for i, pin in enumerate(in_pins):
            if i == 0:
                try:
                    self.rename_pin('din_0', pin)
                except ValueError:
                    continue
            else:
                self.add_pin(pin, TermType.input)

        for i, pin in enumerate(out_pins):
            if i == 0:
                try:
                    self.rename_pin('dout_0<1:0>', pin)
                except ValueError:
                    continue
            else:
                self.add_pin(pin, TermType.output)

        if export_nets:
            for pin in nets_to_export:
                self.add_pin(pin, TermType.inout)
