## Direction

[Direction](https://github.com/NGMAAAYO/Cosmos/blob/9a101853691e34b9c8d3f7b109fbe916e227326b/core/api.py#L2) 类定义了方向的基本概念。

构造方法：core.api.Direction(dx=0, dy=0)  
- dx (int): 方向在`x`轴上的偏移量
- dy (int): 方向在`y`轴上的偏移量


### 方法

#### static def center() -> Direction:

> 返回朝向中间的方向（即原地）

#### static def north() -> Direction:

> 返回朝向北方的方向（即上方）

#### static def north_east() -> Direction:

> 返回朝向东北方的方向

#### static def east() -> Direction:

> 返回朝向东方的方向（即右方）

#### static def south_east() -> Direction:

> 返回朝向东南方的方向

#### static def south() -> Direction:

> 返回朝向南方的方向（即下方）

#### static def south_west() -> Direction:

> 返回朝向西南方的方向

#### static def west() -> Direction:

> 返回朝向西方的方向（即左方）

#### static def north_west() -> Direction:

> 返回朝向西北方的方向

#### static def all_directions() -> list[Direction]:

> 返回一个`list[]`，包含所有方向

#### static def cardinal_directions() -> list[Direction]:

> 返回一个`list[]`，包含东南西北四个方向

#### def get_dx(self) -> int:

> 返回方向在`x`轴上面的偏移量

#### def get_dy(self) -> int:

> 返回方向在`y`轴上面的偏移量

#### def opposite(self) -> Direction:

> 返回方向的反方向

#### def rotate_left(self) -> Direction:

> 返回方向向左偏移`45`度的方向

#### def rotate_right(self) -> Direction:

> 返回方向向右偏移`45`度的方向

#### def equals(self, dir: Direction) -> bool:

> 返回`True`或`False`，表明两个方向是否相等

#### def __eq__(self, dir: Direction) -> bool:

> 重载`==`操作符，表明两个方向是否相等