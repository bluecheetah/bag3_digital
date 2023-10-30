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

from typing import Mapping, Any

import os
import pkg_resources

from bag.design.module import Module
from bag.design.database import ModuleDB
from bag.util.immutable import Param, ImmutableList


# noinspection PyPep8Naming
class bag3_digital__inv_diff_chain(Module):
    """Module for library bag3_digital cell inv_diff_chain.

    Fill in high level description here.
    """

    yaml_file = pkg_resources.resource_filename(__name__,
                                                os.path.join('netlist_info',
                                                             'inv_diff_chain.yaml'))

    def __init__(self, database: ModuleDB, params: Param, **kwargs: Any) -> None:
        Module.__init__(self, self.yaml_file, database, params, **kwargs)

    @classmethod
    def get_params_info(cls) -> Mapping[str, str]:
        return dict(
            inv_diff='Parameters for differential inverter.',
            length='Length of chain; Default is 2.',
            export_nodes='True to label internal nodes; Default is False.',
        )

    @classmethod
    def get_default_param_values(cls) -> Mapping[str, Any]:
        return dict(
            length=2,
            export_nodes=False,
        )

    def design(self, inv_diff: ImmutableList[Param], length: int, export_nodes: bool
               ) -> None:
        if not export_nodes:
            self.remove_pin('mid<0>')
            self.remove_pin('midb<0>')
        if length < 1:
            raise ValueError('Chain must be at least 1 long.')
        if length == 1:
            self.instances['XSTAGE'].design(**inv_diff)
        else:
            # add additional instances
            inst_term_list = []
            last_nets = ('in', 'inb')
            for idx in range(length - 1):
                inst_term_list.append((f'XSTAGE{idx}', [('in', last_nets[0]),
                                                        ('inb', last_nets[1]),
                                                        ('out', f'mid<{idx}>'),
                                                        ('outb', f'midb<{idx}>')]))
                last_nets = (f'mid<{idx}>', f'midb<{idx}>')
            inst_term_list.append((f'XSTAGE{length - 1}', [('in', last_nets[0]),
                                                           ('inb', last_nets[1]),
                                                           ('out', 'out'),
                                                           ('outb', 'outb')]))
            self.array_instance('XSTAGE', inst_term_list=inst_term_list)
            if export_nodes:
                self.rename_pin('mid<0>', f'mid<{length - 2}:0>')
                self.rename_pin('midb<0>', f'midb<{length - 2}:0>')
            # design instances
            for idx in range(length):
                self.instances[f'XSTAGE{idx}'].design(**inv_diff)
