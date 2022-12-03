## Controller

> 定义实体控制器的类

### 方法

#### def get_all_teams(self):

> 返回包含所有队伍的`list`

#### def get_opponent(self):

> 返回包含所有敌对队伍的`list`

#### def get_cooldown_turns(self):

> 返回还有多少回合自身实体才能够行动

#### def get_overdrive_factor(self, team):

> 返回指定队伍的过载增益系数

#### def get_defence(self):

> 返回自身的防护值

#### def get_id(self):

> 返回自身的`ID`

#### def get_location(self):

> 返回自身的位置

#### def get_round_num(self):

> 返回当前的回合数

#### def get_team(self):

> 返回自身的队伍

#### def get_type(self):

> 返回自身的类型

#### def get_radio(self):

> 返回自身的无线电

#### def get_charge_point(self):

> 返回本队最终兵器已有的充能点数

#### def adjacent_location(self, dir):

> 返回自身目标方向相邻的位置

#### def is_opponent(self, team):

> 检查指定队伍是否是敌方

#### def is_blocked(self, d):

> 检查指定方向是否被阻挡

#### def is_location_occupied(self, loc)

> 检查指定位置是否被占用。指定的位置必须在探测范围内

#### def is_ready(self):

> 检查自己是否可以执行动作

#### def on_the_map(self, loc):

> 检查目标位置是否在地图上

#### def can_detect_location(self, loc):

> 检查是否可以探测指定位置

#### def can_detect_radius(self, radius):

> 检查是否可以探测指定半径

#### def can_sense_location(self, loc):

> 检查是否可以感知指定位置

#### def can_sense_radius(self, radius):

> 检查是否可以感知指定半径

#### def sense_entity(self, arg):

> 感知指定`id`或`位置`的实体。如果无法感知则会返回`None`

#### def sense_nearby_entities(self, center=None, radius=None, teams=None):

> 感知附近包括自身在内的所有实体。返回一个包含附近实体信息的`list`
> 
> > `center`为感知的中心点；默认为自身位置
>
> > `radius`为以`center`为中心的感知半径；默认为自身最大感知范围
>
> > 'teams'为包含所有要探测的实体队伍的`list`；默认为所有队伍

#### def detect_nearby_entities(self, radius):

> 探测指定范围内所有的实体。返回一个包含附近实体位置的`list`

#### def sense_aether(self, loc):

> 感知指定位置的以太密度。指定的位置必须在感知范围内

#### def can_charge(self, energy):

> 检查是否可以充指定数量的能

#### def can_build(self, entity_type, dir, energy):

> 检查是否可以以指定的参数建造

#### def can_overdrive(self, radius):

> 检查是否可以在指定半径过载

#### can_analyze(self, arg):

> 检查是否可以分析指定`id`或`位置`的实体

#### def can_move(self, dir):

> 检查是否可以向指定方向移动

#### def can_set_radio(radio):

> 检查是否可以改为指定广播值

#### def charge(self, energy):

> 花费`energy`点为最终兵器充能

#### def build(self, entity_type, dir, energy):

> 以指定的参数建造

#### def overdrive(self, radius):

> 在指定半径过载

#### analyze(self, arg):

> 分析指定`id`或`位置`的实体

#### def move(self, dir):

> 向指定方向移动

#### def set_radio(radio):

> 自身改为指定广播值