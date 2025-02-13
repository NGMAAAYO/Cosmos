## EntityInfo

[EntityInfo](https://github.com/NGMAAAYO/Cosmos/blob/9a101853691e34b9c8d3f7b109fbe916e227326b/core/api.py#L199) 类定义了实体信息的基本概念。

构造方法：core.api.EntityInfo(type)  
- type (str): 实体类型，`destroyer`、`scout`、`miner` 或 `planet`  

### 参数

#### defence: int

> 返回实体的防护值

#### ID: int

> 返回实体的`ID`

#### energy: int

> 返回实体的能量值

#### location: [MapLocation](./MapLocation.md)

> 返回实体的位置

#### team: [Team](./Team.md)

> 返回实体的队伍

#### type: [EntityType](./EntityType.md)

> 返回实体的种类

#### radio: int

> 返回实体的无线电
