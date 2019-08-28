#  Tencent is pleased to support the open source community by making GNES available.
#
#  Copyright (C) 2019 THL A29 Limited, a Tencent company. All rights reserved.
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#  http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

from collections import defaultdict
from functools import reduce
from typing import List, Generator

from ..base import TrainableBase, CompositionalTrainableBase
from ..proto import gnes_pb2, merge_routes


class BaseRouter(TrainableBase):
    """ Base class for the router. Inherit from this class to create a new router.

    Router forwards messages between services. Essentially, it receives a 'gnes_pb2.Message'
    and call `apply()` method on it.
    """

    def apply(self, msg: 'gnes_pb2.Message', *args, **kwargs):
        """
        Modify the incoming message

        :param msg: incoming message
        """
        pass


class BaseMapRouter(BaseRouter):
    def apply(self, msg: 'gnes_pb2.Message', *args, **kwargs) -> Generator:
        pass


class BaseReduceRouter(BaseRouter):
    def apply(self, msg: 'gnes_pb2.Message', accum_msgs: List['gnes_pb2.Message'], *args, **kwargs) -> None:
        """
        Modify the current message based on accumulated messages

        :param msg: the current message
        :param accum_msgs: accumulated messages
        """
        merge_routes(msg, accum_msgs)
        if len(msg.envelope.num_part) > 1:
            msg.envelope.num_part.pop()
        else:
            self.logger.warning(
                'message envelope says num_part=%s, means no further message reducing. '
                'ignore this if you explicitly set "num_part" in RouterService' % msg.envelope.num_part)


class BaseTopkReduceRouter(BaseReduceRouter):
    def __init__(self, reduce_op: str = 'sum', descending: bool = True, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if reduce_op not in {'sum', 'prod', 'max', 'min', 'avg'}:
            raise ValueError('reduce_op=%s is not acceptable' % reduce_op)
        self._reduce_op = reduce_op
        self.descending = descending

    def post_init(self):
        self.reduce_op = {
            'prod': lambda v: reduce((lambda x, y: x * y), v),
            'sum': lambda v: reduce((lambda x, y: x + y), v),
            'max': lambda v: reduce((lambda x, y: max(x, y)), v),
            'min': lambda v: reduce((lambda x, y: min(x, y)), v),
            'avg': lambda v: reduce((lambda x, y: x + y), v) / len(v),
        }[self._reduce_op]

    def get_key(self, x: 'gnes_pb2.Response.QueryResponse.ScoredResult') -> str:
        raise NotImplementedError

    def set_key(self, x: 'gnes_pb2.Response.QueryResponse.ScoredResult', k: str) -> None:
        raise NotImplementedError

    def apply(self, msg: 'gnes_pb2.Message', accum_msgs: List['gnes_pb2.Message'], *args, **kwargs):
        # now convert chunk results to doc results
        all_scored_results = [sr for m in accum_msgs for sr in m.response.search.topk_results]
        score_dict = defaultdict(lambda: {'values': [], 'explains': [], 'reduced_value': 0})

        # count score by iterating over chunks
        for c in all_scored_results:
            k = self.get_key(c)
            score_dict[k]['values'].append(c.score.value)
            score_dict[k]['explains'].append(c.score.explained)

        for k, v in score_dict.items():
            score_dict[k]['reduced_value'] = self.reduce_op(v['values'])

        msg.response.search.ClearField('topk_results')

        # sort and add docs
        for k, v in sorted(score_dict.items(), key=lambda kv: kv[1]['reduced_value'] * (-1 if self.descending else 1)):
            r = msg.response.search.topk_results.add()
            r.score.value = v['reduced_value']
            r.score.explained = ','.join('{%s}' % v['explains'])
            self.set_key(r, k)

        super().apply(msg, accum_msgs)


class PipelineRouter(CompositionalTrainableBase):
    def apply(self, *args, **kwargs) -> None:
        if not self.components:
            raise NotImplementedError
        for be in self.components:
            be.apply(*args, **kwargs)
