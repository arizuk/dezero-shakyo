import numpy as np
import unittest
import heapq
import weakref
import contextlib

def as_array(x):
    if np.isscalar(x):
        return np.array(x)
    return x

def numerical_diff(f, x, eps=1e-4):
    x0 = Variable(x.data - eps)
    x1 = Variable(x.data + eps)
    y0 = f(x0)
    y1 = f(x1)
    return (y1.data - y0.data) / (2*eps)

class SquareTest(unittest.TestCase):
    def test_forward(self):
        x = Variable(np.array(2.0))
        y = square(x)
        expected = np.array(4.0)
        self.assertEqual(y.data, expected)
    
    def test_backward(self):
        x = Variable(np.array(3.0))
        y = square(x)
        y.backward()
        expected = np.array(6.0)
        self.assertEqual(x.grad, expected)

    def test_gradient_check(self):
        x = Variable(np.random.rand(1))
        y = square(x)
        y.backward()
        num_grad = numerical_diff(square, x)
        flg = np.allclose(x.grad, num_grad)
        self.assertTrue(flg)

class Config:
    enable_backprop = True

@contextlib.contextmanager
def using_config(name, value):
    old_value = getattr(Config, name)
    setattr(Config, name, value)
    try:
        yield
    finally:
        setattr(Config, name, old_value)

def no_grad():
    return using_config('enable_backprop', False)

class Variable:
    def __init__(self, data):
        if data is not None:
            if not isinstance(data, np.ndarray):
                raise TypeError("{} is not supported".format(type(data)))

        self.data = data
        self.grad = None
        self.creator = None
        self.generation = 0
    
    def set_creator(self, func):
        self.creator = func
        self.generation = func.generation + 1

    def backward(self, retain_grad=False):
        if self.grad is None:
            self.grad = np.ones_like(self.data)

        hq = []
        funcs = {}
        func_idx = 0
        seen_set = set()

        def add_func(f):
            if f not in seen_set:
                nonlocal func_idx
                func_idx += 1
                funcs[func_idx] = f
                heapq.heappush(hq, (-f.generation, func_idx))
                seen_set.add(f)
        
        def pop():
            _, idx = heapq.heappop(hq)
            return funcs.pop(idx)

        add_func(self.creator)

        while funcs:
            f = pop()
            gys = [output().grad for output in f.outputs]
            gxs = f.backward(*gys)
            if not isinstance(gxs, tuple):
                gxs = (gxs,)

            for x, gx in zip(f.inputs, gxs):

                if x.grad is None:
                    x.grad = gx
                else:
                    # x.grad += gx # this code don't work
                    x.grad = x.grad + gx

                if x.creator is not None:
                    add_func(x.creator)
            
            if not retain_grad:
                for y in f.outputs:
                    y().grad = None
    
    def cleargrad(self):
        self.grad = None

class Function:
    def __call__(self, *inputs):
        xs = [x.data for x in inputs]
        ys = self.forward(*xs)
        if not isinstance(ys, tuple):
            ys = (ys,)

        outputs = [Variable(as_array(y)) for y in ys]

        if Config.enable_backprop:
            self.generation = max([x.generation for x in inputs])

            for output in outputs:
                output.set_creator(self)
            self.inputs = inputs
            self.outputs = [weakref.ref(output) for output in outputs]

        return outputs if len(outputs) > 1 else outputs[0]

    def forward(self, x):
        raise NotImplementedError()

    def backward(self, gy):
        raise NotImplementedError()

class Add(Function):
    def forward(self, x0, x1):
        y = x0 + x1
        return y

    def backward(self, gy):
        return gy, gy

class Square(Function):
    def forward(self, x):
        y = x ** 2
        return y

    def backward(self, gy):
        x = self.inputs[0].data
        gx = 2 * x * gy
        return gx


def add(x0, x1):
    return Add()(x0, x1)

def square(x):
    return Square()(x)

if __name__ == "__main__":
    with no_grad():
        x = Variable(np.array(2.0))
        y = square(x)