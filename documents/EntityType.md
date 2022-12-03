## EntityType

> 定义实体类型的基本类
> 
> 构造：`EntityType("type")`

### 参数

#### name

> 返回当前实体的种类，在`["destroyer", "scout", "miner", "planet"]`之间

#### action_cooldown

> 返回当前实体的基础冷却值

#### action_radius

> 返回当前实体的行动半径

#### defence_ratio

> 返回当前实体初始防护值和初始能量值的转化比例

#### detection_radius

> 返回当前实体的探测半径

#### initial_cooldown

> 返回当前实体的初始冷却值

#### sensor_radius

> 返回当前实体的感知半径

### 方法

#### def all_types():

> 返回一个`list`，包含所有的实体种类
