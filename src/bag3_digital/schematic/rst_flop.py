# SPDX-License-Identifier: Apache-2.0
# Copyright 2019 Blue Cheetah Analog Design Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# -*- coding: utf-8 -*-

from typing import Mapping, Any, Union

import pkg_resources
from pathlib import Path

from bag.design.module import Module
from bag.design.database import ModuleDB
from bag.util.immutable import Param
from pybag.enum import TermType

from ..layout.stdcells.util import RstType


# noinspection PyPep8Naming
class bag3_digital__rst_flop(Module):
    """Module for library bag3_digital cell rst_flop.

    Fill in high level description here.
    """

    yaml_file = pkg_resources.resource_filename(__name__,
                                                str(Path('netlist_info',
                                                         'rst_flop.yaml')))

    def __init__(self, database: ModuleDB, params: Param, **kwargs: Any) -> None:
        Module.__init__(self, self.yaml_file, database, params, **kwargs)

    @classmethod
    def get_params_info(cls) -> Mapping[str, str]:

        return dict(
            m_params='Master Parameters',
            s_params='Slave Parameters',
            inv_params='Inverter Params',
            rst_type='SET or RESET; RESET by default',
        )

    @classmethod
    def get_default_param_values(cls) -> Mapping[str, Any]:
        return dict(rst_type=RstType.RESET, inv_params=None)

    def get_master_basename(self) -> str:
        rst_type: Union[str, RstType] = self.params['rst_type']
        if isinstance(rst_type, str):
            rst_type = RstType[rst_type]
        if rst_type is RstType.SET:
            return 'set_flop'
        return 'rst_flop'

    def design(self, m_params: Param, s_params: Param, inv_params: Param, rst_type: Union[str, RstType]) -> None:
        self.instances['XM'].design(**m_params)
        self.instances['XS'].design(**s_params)
        if inv_params:
            self.instances['XB'].design(**inv_params)
        else:
            self.add_pin('clkb', TermType.input)
            self.delete_instance('XB')

        if isinstance(rst_type, str):
            rst_type = RstType[rst_type]
        if rst_type is RstType.SET:
            self.rename_pin('rst', 'setb')
            self.reconnect_instance_terminal('XM', 'setb', 'setb')
            self.reconnect_instance_terminal('XS', 'setb', 'setb')
