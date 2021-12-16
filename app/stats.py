import time
from functools import wraps

class Statrec:
    def __init__(self):
        self.count = 0
        self.time = 0
    
    def add(self, t):
        self.count += 1
        self.time += t

    def average(self):
        return self.time / self.count

class Statstore:
    def __init__(self, name=''):
        self.stats = {}
        self.name = name

    def add(self, name, t):
        if name not in self.stats:
            self.stats[name] = Statrec()
        self.stats[name].add(t)

    def report(self):
        if self.stats:
            print(f' **************  {self.name}  *************** ')
            print('FUNCTION                    CALLS    AVERAGE      TOTAL')
            sl = sorted(self.stats, key=lambda x: self.stats[x].time)
            for func in sl:
                print(f'{func:20} : {self.stats[func].count:10.0f} {self.stats[func].average():10.4f} {self.stats[func].time:10.4f}')
            print(' ********************************************* ')

def stats(func):
    def inner(*args, **kwargs):
        starttime = time.time()
        result = func(*args, **kwargs)
        statstore.add(func.__name__, time.time() - starttime)
        return result
    inner = wraps(func)(inner)
    return inner

statstore = Statstore()

