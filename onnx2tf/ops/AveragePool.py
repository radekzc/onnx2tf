import random
random.seed(0)
import numpy as np
np.random.seed(0)
import tensorflow as tf
import onnx_graphsurgeon as gs
from tensorflow.python.keras.layers import (
    AveragePooling1D,
    AveragePooling2D,
    AveragePooling3D,
)
from utils.colors import Color
from utils.common_functions import (
    calc_pads_same_pooling,
    pad_input,
)


def make_node(
    *,
    graph_node: gs.Node,
    tf_layers_dict: dict,
    **kwargs: dict,
):
    """AveragePool

    Parameters
    ----------
    graph_node: gs.Node
        graph_surgeon Node

    tf_layers_dict: dict
        optype, shape, dtype, tensorflow graph
    """
    graph_node_input: gs.Variable = graph_node.inputs[0]
    graph_node_output: gs.Variable = graph_node.outputs[0]
    shape = graph_node_output.shape
    dtype = graph_node_output.dtype

    x = tf_layers_dict[graph_node_input.name]['tf_node']

    # 0: False, 1: True
    ceil_mode = bool(graph_node.attrs.get('ceil_mode', 0))
    # 0: False, 1: True
    count_include_pad = bool(graph_node.attrs.get('count_include_pad', 0))
    kernel_shape = graph_node.attrs['kernel_shape']
    spatial_size = len(kernel_shape)
    x_rank = spatial_size + 2
    strides = graph_node.attrs.get('strides', [1] * spatial_size)
    dilations = graph_node.attrs.get('dilations', [1] * spatial_size)
    is_known_shape = x.shape.is_fully_defined()

    # Immediately after the input OP, transpose according to 1D, 2D, or 3D
    transposed_tensor = None
    if tf_layers_dict[graph_node_input.name]['optype'] == 'Input':
        if spatial_size == 1:
            transposed_tensor = tf.transpose(x, perm=[0,2,1])
        elif spatial_size == 2:
            transposed_tensor = tf.transpose(x, perm=[0,2,3,1])
        elif spatial_size == 3:
            transposed_tensor = tf.transpose(x, perm=[0,2,3,4,1])
        else:
            error_msg = f'' +\
                f'{Color.RED}ERROR:{Color.RESET} ' +\
                f'AveragePool supports only 1D, 2D, and 3D. ' +\
                f'opname: {graph_node.name} Type: AveragePool{len(kernel_shape)}D'
            print(error_msg)
            assert False, error_msg

    pads = graph_node.attrs.get('auto_pad', 'NOTSET')
    if pads == 'NOTSET':
        pads = graph_node.attrs.get('pads', [0] * spatial_size * 2)
        if is_known_shape and pads != [0] * spatial_size * 2:
            in_shape = transposed_tensor.get_shape()
            same_paddings = calc_pads_same_pooling(
                in_spatial_shape=in_shape[1:x_rank - 1],
                kernel_shape=kernel_shape,
                strides=strides,
                dilations=dilations,
                padding='SAME_UPPER',
            )
            if pads == same_paddings:
                pads = 'SAME_UPPER'

    is_explicit_padding = type(pads) is list
    padding_ = ''

    if is_explicit_padding or pads == 'SAME_LOWER' or (pads == 'SAME_UPPER' and count_include_pad):
        # pad the input
        padded_tensor = pad_input(
            input_tensor=transposed_tensor,
            is_known_shape=is_known_shape,
            kernel_shape=kernel_shape,
            ceil_mode=ceil_mode,
            spatial_size=spatial_size,
            strides=strides,
            dilations=dilations,
            padding=pads,
            padding_constant=0,
        )
        padding_ = 'valid'

    elif pads == 'SAME_UPPER':
        padded_tensor = transposed_tensor
        padding_ = 'same'

    else:
        padded_tensor = transposed_tensor
        padding_ = 'same'

    # Preserving Graph Structure (Dict)
    tf_layers_dict[graph_node_output.name] = {
        'optype': graph_node.op,
        'shape': shape,
        'dtype': dtype,
    }

    # Generation of TF OP
    if len(kernel_shape) == 1:
        pooled_tensor = AveragePooling1D(
            pool_size=kernel_shape,
            strides=strides,
            padding=padding_
        )(padded_tensor)

    elif len(kernel_shape) == 2:
        pooled_tensor = AveragePooling2D(
            pool_size=kernel_shape,
            strides=strides,
            padding=padding_
        )(padded_tensor)

    elif len(kernel_shape) == 3:
        pooled_tensor = AveragePooling3D(
            pool_size=kernel_shape,
            strides=strides,
            padding=padding_
        )(padded_tensor)

    else:
        error_msg = f'' +\
            f'{Color.RED}ERROR:{Color.RESET} ' +\
            f'AveragePool supports only 1D, 2D, and 3D. ' +\
            f'opname: {graph_node.name} Type: AveragePool{len(kernel_shape)}D'
        print(error_msg)
        assert False, error_msg

    tf_layers_dict[graph_node_output.name]['tf_node'] = pooled_tensor