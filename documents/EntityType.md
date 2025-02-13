## EntityType

[EntityType](https://github.com/NGMAAAYO/Cosmos/blob/9a101853691e34b9c8d3f7b109fbe916e227326b/core/api.py#L143) 类定义了实体类型的基本概念。

构造方法：core.api.EntityType(type)  
- type (str): 实体类型，`destroyer`、`scout`、`miner` 或 `planet`  

### 属性

#### name: str
> 返回实体的种类。

#### action_cooldown: float
> 返回实体的基础冷却值。

#### action_radius: int
> 返回实体的行动半径。

#### defence_ratio: float
> 返回实体初始防护值与初始能量值之间的转化比例。

#### detection_radius: int
> 返回实体的探测半径。

#### initial_cooldown: int
> 返回实体的初始冷却值。

#### sensor_radius: int
> 返回实体的感知半径。

### 方法

#### static def all_types() -> list[EntityType]
> 返回一个包含所有实体种类的列表。

#### def __eq__(etype: Union[EntityType, str]) -> bool
> 判断当前实体类型是否与另一个实体类型相同。