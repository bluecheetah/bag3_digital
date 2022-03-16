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

from typing import Mapping, Any

import pkg_resources
from pathlib import Path

from bag.design.module import Module
from bag.design.database import ModuleDB
from bag.util.immutable import Param

from pybag.enum import TermType


# noinspection PyPep8Naming
class bag3_digital__ser2Nto2_fast(Module):
    """Module for library bag3_digital cell ser2Nto2_fast.

    Fill in high level description here.
    """

    yaml_file = pkg_resources.resource_filename(__name__,
                                                str(Path('netlist_info',
                                                         'ser2Nto2_fast.yaml')))

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
            ser='Parameters for each serNto1',
            rst_sync='Parameters for reset_sync',
            export_nets='True to export intermediate nets; False by default',
        )

    @classmethod
    def get_default_param_values(cls) -> Mapping[str, Any]:
        return dict(export_nets=False)

    def get_master_basename(self) -> str:
        ratio: int = self.params['ser']['ratio']
        return f'ser_{2 * ratio}to2'

    def design(self, ser: Mapping[str, Any], rst_sync: Mapping[str, Any], export_nets: bool) -> None:
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
        # reset_sync
        self.instances['XRST_SYNC'].design(**rst_sync)
        self.reconnect_instance_terminal('XRST_SYNC', 'clkb', 'clkb')

        # serNto1
        for idx in range(2):
            self.instances[f'XSER{idx}'].design(**ser)
            self.reconnect_instance_terminal(f'XSER{idx}', 'rstb_sync_in', 'rstb_sync')
        ratio: int = self.params['ser']['ratio']

        self.rename_pin('din', f'din<{2 * ratio - 1}:0>')
        suf = f'<{ratio - 1}:0>'
        self.reconnect_instance_terminal('XSER0', f'din{suf}', f'din<{2 * ratio - 2}:0:2>')
        self.reconnect_instance_terminal('XSER1', f'din{suf}', f'din<{2 * ratio - 1}:1:2>')

        if export_nets:
            self.add_pin('clk_buf<1:0>', TermType.output)
            self.add_pin('clkb_buf<1:0>', TermType.output)
            self.add_pin('rstb_sync', TermType.output)
