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

from typing import Mapping, Any, Optional

import pkg_resources
from pathlib import Path

from pybag.enum import TermType

from bag.design.module import Module
from bag.design.database import ModuleDB
from bag.util.immutable import Param


# noinspection PyPep8Naming
class bag3_digital__clk_gate(Module):
    """Module for library bag3_digital cell clk_gate.

    Fill in high level description here.
    """

    yaml_file = pkg_resources.resource_filename(__name__,
                                                str(Path('netlist_info',
                                                         'clk_gate.yaml')))

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
            dff_params='DFF parameters for en synchronization',
            num_dff='Number of cascaded DFFs for synchronization',
            nand_params='Nand parameters for clock gating.',
            gclk_inv_params='Inverter parameter to generate gclk',
            clkb_inv_params='Optional inverter parameters to generate clkb. If None, clkb is an input pin.'
                            ' Defaults to None.',
            en_buf_params='Optional inverter chain parameters to buffer en. If None, removed. Defaults to None.',
            export_nets='True to export intermediate nets. Defaults to False',
        )

    @classmethod
    def get_default_param_values(cls) -> Mapping[str, Any]:
        return dict(clkb_inv_params=None, en_buf_params=None, export_nets=False)

    def design(self, dff_params: Param, num_dff: int, nand_params: Param, gclk_inv_params: Param,
               clkb_inv_params: Optional[Param],
               en_buf_params: Optional[Param], export_nets: bool) -> None:
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
        self.instances['XSYNC'].design(**dff_params)
        self.instances['XNAND'].design(**nand_params.copy(append=dict(num_in=2)))
        self.instances['XGCLK'].design(**gclk_inv_params)

        self.reconnect_instance_terminal('XSYNC', 'clkb', 'clk')
        if num_dff > 1:
            en_sync_mid_net = f'en_sync_mid<{num_dff - 2}:0>' if num_dff > 2 else 'en_sync_mid'
            dff_conns = {
                'in': f'{en_sync_mid_net},en_buf',
                'out': f'en_sync,{en_sync_mid_net}'
            }
            self.rename_instance('XSYNC', f'XSYNC<{num_dff - 1}:0>', dff_conns.items())

        nets_to_export = {'en_sync', 'gclkb'}

        if clkb_inv_params is None:
            self.remove_instance('XCLKB')
            self.add_pin('clkb', TermType.input)
        else:
            self.instances['XCLKB'].design(**clkb_inv_params)
            nets_to_export.add('clkb')

        if en_buf_params is None:
            self.remove_instance('XENBUF')
            self.reconnect_instance_terminal('XSYNC', 'in', 'en')
        else:
            self.instances['XENBUF'].design(**en_buf_params)
            nets_to_export.add('en_buf')

        if export_nets:
            for pin in nets_to_export:
                self.add_pin(pin, TermType.inout)
