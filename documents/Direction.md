## Direction

> 定义方向的基本类
> 
> 构造：`Direction(dx, dy)`

### 方法

#### def center():

> 返回朝向中间的方向（即原地）

#### def north():

> 返回朝向北方的方向（即上方）

#### def north_east():

> 返回朝向东北方的方向

#### def east():

> 返回朝向东方的方向（即右方）

#### def south_east():

> 返回朝向东南方的方向

#### def south():

> 返回朝向南方的方向（即下方）

#### def south_west():

> 返回朝向西南方的方向

#### def west():

> 返回朝向西方的方向（即左方）

#### def north_west():

> 返回朝向西北方的方向

#### def all_directions():

> 返回一个`list[]`，包含所有方向

#### def cardinal_directions():

> 返回一个`list[]`，包含东南西北四个方向

#### def get_dx(self):

> 返回方向在`x`轴上面的偏移量

#### def get_dy(self):

> 返回方向在`y`轴上面的偏移量

#### def opposite(self):

> 返回方向的反方向

#### def rotate_left(self):

> 返回方向向左偏移`45`度的方向

#### def rotate_right(self):

> 返回方向向右偏移`45`度的方向

#### def equals(self, dir):

> 返回`True`或`False`，表明两个方向是否相等
