import numpy as np
import unittest
import heapq
import weakref
import contextlib

def as_array(x):
    if np.isscalar(x):
        return np.array(x)
    return x

def as_variable(obj):
    if isinstance(obj, Variable):
        return obj
    return Variable(obj)

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
    __array_priority__ = 200 # ndarrayのmulよりVariableのrmulの優先度をあげる

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

    @property
    def shape(self):
        return self.data.shape

    @property
    def ndim(self):
        return self.data.ndim

    @property
    def size(self):
        return self.data.size

    @property
    def dtype(self):
        return self.data.dtype

    def __len__(self):
        return len(self.data)

    def __repr__(self):
        if self.data is None:
            return 'variable(None)'
        p = str(self.data).replace('\n', '\n' + ' ' * 9)
        return 'variable(' + p + ')'

class Function:
    def __call__(self, *inputs):
        inputs = [as_variable(x) for x in inputs]

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

class Neg(Function):
    def forward(self, x):
        return -x

    def backward(self, gy):
        return -gy

class Add(Function):
    def forward(self, x0, x1):
        y = x0 - x1
        return y

    def backward(self, gy):
        return gy, -gy

class Sub(Function):
    def forward(self, x0, x1):
        y = x0 - x1
        return y

    def backward(self, gy):
        return gy, gy

class Mul(Function):
    def forward(self, x0, x1):
        y = x0 * x1
        return y

    def backward(self, gy):
        x0, x1 = self.inputs[0].data, self.inputs[1].data
        return gy * x1, gy * x0

class Div(Function):
    def forward(self, x0, x1):
        y = x0 / x1
        return y

    def backward(self, gy):
        x0, x1 = self.inputs[0].data, self.inputs[1].data
        gx0 = gy / x1
        gx1 = gy * (-x0 / x1 ** 2)
        return gx0, gx1

class Pow(Function):
    def __init__(self, c):
        self.c = c

    def forward(self, x):
        y = x ** self.c
        return y

    def backward(self, gy):
        x = self.inputs[0].data
        c = self.c
        gx = c * x**(c-1) * gy
        return gx

def neg(x):
    return Neg()(x)

def add(x0, x1):
    x1 = as_array(x1)
    return Add()(x0, x1)

def sub(x0, x1):
    x1 = as_array(x1)
    return Sub()(x0, x1)

def rsub(x0, x1):
    x1 = as_array(x1)
    return Sub()(x1, x0)

def mul(x0, x1):
    x1 = as_array(x1)
    return Mul()(x0, x1)

def div(x0, x1):
    x1 = as_array(x1)
    return Div()(x0, x1)

def rdiv(x0, x1):
    x1 = as_array(x1)
    return Div()(x1, x0)

def pow(x, c):
    return Pow(c)(x)

Variable.__neg__ = neg
Variable.__add__ = add
Variable.__radd__ = add
Variable.__sub__ = sub
Variable.__rsub__ = rsub
Variable.__mul__ = mul
Variable.__rmul__ = mul
Variable.__truediv__ = div
Variable.__rtruediv__ = rdiv
Variable.__pow__ = pow

class Square(Function):
    def forward(self, x):
        y = x ** 2
        return y

    def backward(self, gy):
        x = self.inputs[0].data
        gx = 2 * x * gy
        return gx

def square(x):
    return Square()(x)

if __name__ == "__main__":
    # neg
    x = Variable(np.array(2.0))
    y = -x
    print(y)
    assert y.data == -2

    # sub
    x = Variable(np.array(2.0))
    y1 = 2.0 - x
    y2 = x - 1.0
    print(y1)
    print(y2)
    assert y1.data == 0.0
    assert y2.data == 1.0

    # div
    x = Variable(np.array(4.0))
    y1 = x / 2.0
    y2 = 12.0 / x
    print(y1)
    print(y2)
    assert y1.data == 2.0
    assert y2.data == 3.0

    # pow
    x = Variable(np.array(2.0))
    y = x ** 3
    print(y)
    assert y.data == 8.0
