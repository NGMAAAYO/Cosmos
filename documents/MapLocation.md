## MapLocation 类

[MapLocation](https://github.com/NGMAAAYO/Cosmos/blob/9a101853691e34b9c8d3f7b109fbe916e227326b/core/api.py#L90) 类定义了地图上位置的基本概念，并提供了一系列操作方法。通过这些方法可以实现位置的平移、方向判断与距离计算等功能。

构造方法：core.api.MapLocation(x: int, y: int)  
- x: int — X 坐标  
- y: int — Y 坐标  

### 方法

#### def add(self, dir: [Direction](Direction.md)) -> MapLocation
> 返回当前位置按照给定方向移动一格后的新位置。  
> 参数：  
> - dir ([Direction](Direction.md)): 表示移动方向的 [Direction](Direction.md) 对象。 
> 
> 返回：  
> - MapLocation: 移动后的新位置。

#### def direction_to(self, loc: MapLocation) -> [Direction](Direction.md)
> 计算从当前点指向目标点的粗略方向。  
> 参数：  
> - loc (MapLocation): 目标位置。  
> 
> 返回：  
> - [Direction](Direction.md): 从当前位置指向目标位置的方向。

#### def distance_to(self, loc: MapLocation) -> int
> 计算当前位置与目标位置之间的平方距离，适用于无需精确欧几里得距离时的比较。  
> 参数：  
> - loc (MapLocation): 目标位置。  
> 
> 返回：  
> - int: 当前位置与目标位置之间的平方距离。

#### def is_adjacent_to(self, loc: MapLocation) -> bool
> 判断目标位置是否与当前位置相邻（包括对角线相邻）。  
> 参数：  
> - loc (MapLocation): 目标位置。  
> 
> 返回：  
> - bool: 如果相邻返回 True，否则返回 False。

#### def subtract(self, dir: [Direction](Direction.md)) -> MapLocation
> 返回当前位置按照给定方向的反方向移动一格后的新位置。  
> 参数：  
> - dir ([Direction](Direction.md)): 表示移动方向的 [Direction](Direction.md) 对象。
> 
> 返回：  
> - MapLocation: 移动后的新位置。

#### def translate(self, dx: int, dy: int) -> MapLocation
> 返回当前位置经过横向偏移 dx 和纵向偏移 dy 后的新位置。  
> 参数：  
> - dx (int): 横向偏移量（正表示向右，负表示向左）。  
> - dy (int): 纵向偏移量（正表示向下，负表示向上）。  
> 
> 返回：  
> - MapLocation: 平移后的新位置。

#### def equals(self, loc: MapLocation) -> bool
> 判断目标位置与当前位置是否完全相同（坐标相同）。也可以直接使用 == 运算符。
> 参数：  
> - loc (MapLocation): 目标位置。  
> 
> 返回：  
> - bool: 如果两个位置的 x 和 y 坐标均相等则返回 True，否则返回 False。
