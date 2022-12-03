## MapLocation

> 定义地图位置的基本类
> 
> 构造：`MapLocation(x, y)`

### 方法

#### def add(self, dir):

> 返回当前位置向目标方向移动一格后的位置

#### def direction_to(self, loc):

> 返回目标位置在当前位置的什么方向（粗略估计）

#### def distance_to(self, loc):

> 返回当前位置到目标位置的平方距离

#### def is_adjacent_to(self, loc):

> 返回True或False，判断目标位置是否与当前位置相邻

#### def subtract(self, dir):

> 返回当前位置向目标方向的反方向移动一格后的位置

#### def translate(self, dx, dy):

> 返回当前位置加上`dx`加上`dy`后的位置

#### def equals(self, loc):

> 返回`True`或`False，判断目标位置是否与当前位置相等
