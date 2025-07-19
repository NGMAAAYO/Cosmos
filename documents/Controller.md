## Controller

[Controller](https://github.com/NGMAAAYO/Cosmos/blob/9a101853691e34b9c8d3f7b109fbe916e227326b/core/entity.py#L8) 类定义了实体控制器。

```python
from core.entity import Controller
```

### 方法

#### def get_all_teams(self) -> list[[Team](Team.md)]:

> 返回包含所有队伍的`list`

#### def get_opponent(self) -> list[[Team](Team.md)]:

> 返回包含所有敌对队伍的`list`

#### def get_cooldown_turns(self) -> int:

> 返回还有多少回合自身实体才能够行动

#### def get_overdrive_factor(self, team: [Team](Team.md), round: int = 0) -> float:

> 返回指定队伍在 `round` 回合后的过载增益系数。`round` 必须大于等于 0

#### def get_defence(self) -> int:

> 返回自身的防护值

#### def get_energy(self) -> int:

> 返回自身的能量值

#### def get_id(self) -> int:

> 返回自身的`ID`

#### def get_location(self) -> [MapLocation](MapLocation.md):

> 返回自身的位置

#### def get_round_num(self) -> int:

> 返回当前的回合数

#### def get_team(self) -> [Team](Team.md):

> 返回自身的队伍

#### def get_type(self) -> [EntityType](EntityType.md):

> 返回自身的类型

#### def get_radio(self) -> int:

> 返回自身的无线电

#### def get_charge_point(self) -> int:

> 返回本队最终兵器已有的充能点数

#### def get_entity_count(self) -> int:

> 返回本队总实体数量

#### def adjacent_location(self, dir: [Direction](Direction.md)) -> [MapLocation](MapLocation.md):

> 返回自身目标方向相邻的位置

#### def is_opponent(self, team: [Team](Team.md)) -> bool:

> 检查指定队伍是否是敌方

#### def is_blocked(self, d: [Direction](Direction.md)) -> bool:

> 检查指定方向是否被阻挡

#### def is_location_occupied(self, loc: [MapLocation](MapLocation.md)) -> bool:

> 检查指定位置是否被占用。指定的位置必须在探测范围内

#### def is_ready(self) -> bool:

> 检查自己是否可以执行动作

#### def on_the_map(self, loc: [MapLocation](MapLocation.md)) -> bool:

> 检查目标位置是否在地图上。指定的位置必须在探测范围内

#### def can_detect_location(self, loc: [MapLocation](MapLocation.md)) -> bool:

> 检查是否可以探测指定位置

#### def can_detect_radius(self, radius: int) -> bool:

> 检查是否可以探测指定半径

#### def can_sense_location(self, loc: [MapLocation](MapLocation.md)) -> bool:

> 检查是否可以感知指定位置

#### def can_sense_radius(self, radius: int) -> bool:

> 检查是否可以感知指定半径

#### def sense_entity(self, arg: Union[int, [MapLocation](MapLocation.md)]) -> Optional[[EntityInfo](EntityInfo.md)]:

> 感知指定`id`或`位置`的实体。如果无法感知则会返回`None`

#### def sense_nearby_entities(self, center: Optional[[MapLocation](MapLocation.md)] = None, radius: Optional[int] = None, teams: Optional[list[[Team](Team.md)]] = None) -> list[[EntityInfo](EntityInfo.md)]:

> 感知附近包括自身在内的所有实体。  
> 
> 参数：  
> - center (可选): 感知的中心点；默认为自身位置。  
> - radius (可选): 以 center 为中心的感知半径；默认为自身最大感知范围。  
> - teams (可选): 包含所有要探测的实体队伍的 list；默认为所有队伍。  
> 
> 返回：  
> - list: 包含附近实体信息的列表

#### def detect_nearby_entities(self, radius: int) -> list[[MapLocation](MapLocation.md)]:

> 探测指定范围内所有的实体。返回一个包含附近实体位置的`list`

#### def sense_aether(self, loc: [MapLocation](MapLocation.md)) -> int:

> 感知指定位置的以太密度。指定的位置必须在感知范围内

#### def can_charge(self, energy: int) -> bool:

> 检查是否可以充指定数量的能

#### def can_build(self, entity_type: [EntityType](EntityType.md), dir: [Direction](Direction.md), energy: int) -> bool:

> 检查是否可以以指定的参数建造

#### def can_overdrive(self, radius: int) -> bool:

> 检查是否可以在指定半径过载

#### def can_analyze(self, arg: Union[int, [MapLocation](MapLocation.md)]) -> bool:

> 检查是否可以分析指定`id`或`位置`的实体

#### def can_move(self, dir: [Direction](Direction.md)) -> bool:

> 检查是否可以向指定方向移动

#### def can_set_radio(radio: int) -> bool:

> 检查是否可以改为指定广播值

#### def charge(self, energy: int):

> 花费`energy`点为最终兵器充能

#### def build(self, entity_type: [EntityType](EntityType.md), dir: [Direction](Direction.md), energy: int):

> 以指定的参数建造

#### def overdrive(self, radius: int):

> 在指定半径过载

#### def analyze(self, arg: Union[int, [MapLocation](MapLocation.md)]) -> Optional[[EntityInfo](EntityInfo.md)]:

> 分析指定`id`或`位置`的实体

#### def move(self, dir: [Direction](Direction.md)):

> 向指定方向移动

#### def set_radio(radio: int):

> 自身改为指定广播值
