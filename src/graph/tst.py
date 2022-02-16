y = 0


def f():
    global y
    y += 1
    x = y

    def g():
        nonlocal x

        x += 1
        print(x)

    g.a = 1111
    return g


f()()
f()()
f()()
f()()
print(f().a)
