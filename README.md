# Cosmos - 宙

## 一、背景介绍

《宙》是以原生Python为引擎的实时策略游戏。在游戏当中，多名玩家将分别扮演不同的文明，并且相互对抗。所有玩家的目的均为彻底消灭其他竞争者，并取得最终的胜利。

> 在《宙》的世界中，有一个恒星系统，其中有数个拥有生命的星球。这些星球的历史悠久，在它们的表面上，文明已经成长为技术先进的社会。
> 
> 在这些星球中，有各种各样的文明，它们有着不同的文化、政治体系、经济体系和科技水平。有些文明崇尚和平，有些文明则追求暴力和征服。
> 
> 玩家将扮演这些文明的领导者，谨慎地进行决策，以获得最大的优势。
> 
> 然而，一场战争的代价是惨重的。玩家需要权衡利弊，并且要确保自己的文明不会被摧毁。最终，只有一个文明能够存活下来，并成为最终的胜利者。

## 二、环境

在《宙》当中，玩家需要编写代码来控制己方的实体。比赛是回合制的，并且每场比赛将有`1000`回合。每一个回合中，每一个仍然在场上的实体将有一次运行的机会。

### ① 地图

每一场比赛的地图将是一副二维的、大小在`(32 × 32)`与`(100 × 100)`之间的平面直角坐标系。

地图的每一格会有不同的以太密度。以太密度是一个在`0.1`与`1.0`之间的小数，以太密度越高代表在当前的格子上行动的冷却值越低。

地图上将会有一些星球作为实体存在。星球不可被摧毁、创造，只能够被易主。在游戏开始时，每方将会有`1`到`3`个初始星球，地图上最多将会有`6`个中立的星球。

公平起见，地图上的一切元素都是对称的。

### ② 能量点

星球可以产出能量点，能量点可用于建造新的实体或者用以为最终兵器充能。能量点只能由星球或者特殊实体产出，并且星球之间的能量点不能共享。

### ③ 充能

每一回合，玩家的星球都需要使用一部分能量点来给最终兵器充能。花费最多能量点的队伍将会产生能量共鸣，其最终兵器将会累计一个能量点。

## 三、实体

每个实体将会在一份独立的实例上运行，并且被分配一个随机的、不重复的、不小于`10000`的五位独有ID。

对于每个实体，行动包括移动和它的独特能力。除被动能力之外的每次行动都会导致冷却值上升，并且实体只能在其冷却值小于`1.0`时执行行动。

不同类型的实体具有不同的基本冷却值，执行行动后实体的冷却值将增加基本冷却值除以当前地图方块的以太密度。

无论实体是否选择执行动作，它的冷却值在每一回合都会减一。

### ① 属性

每个实体都具有能量值与防护值两个属性。玩家的星球可以通过消耗部分能量点来制造除星球以外的实体。能量点被表示为`E`。新建的战列舰和侦查舰将会有`10`点初始冷却值。

|   \   |  星球   |  战列舰   |  开采舰   |  侦查舰   |
|:-----:|:-----:|:------:|:------:|:------:|
|  能量点  | 不可创建  |   E    |   E    |   E    |
| 最低能量值 |   无   |   1    |   1    |   1    |
| 初始防护值 | 当前能量值 | ⌈1.0E⌉ | ⌈1.0E⌉ | ⌈0.7E⌉ |
| 初始冷却值 |   0   |   10   |   0    |   10   |
| 基本冷却值 |  2.0  |  1.0   |  2.0   |  1.5   |
| 行动半径  |   2   |   9    |   0    |   12   |
| 感知半径  |  40   |   25   |   20   |   30   |
| 探测半径  |  40   |   25   |   20   |   40   |
| 真实视野  |   是   |   否    |   否    |   是    |
|  能力   | 建造、充能 |   过载   | 开采、进化  |   分析   |

### **注意：平方距离**

为了方便起见，游戏中的一切距离都以平方距离计算。举例说明，两个`x`坐标相差`3`格，`y`坐标相差`4`格的位置的平方距离等于`3 × 3 + 4 × 4 = 25`，即实际距离（欧几里得距离）的平方。

本文档中所提到的一切“距离”均指平方距离。

### ② 移动

除星球以外的实体可以向相邻的、未被占据的位置移动。在满足以下条件时，移动将会被成功执行：

一、实体的冷却值小于`1`。

二、目标位置与当前位置相邻（即周围的`8`格）。

三、目标位置没有被其他实体占据。

移动后，实体的冷却值将增加。

### ③ 感知、探测和视野

地图上的每一个方块都有以太密度，每一个实体都有包括类型、能量值、防护值在内的属性。

所有的实体都可以感知周围方块的以太密度和在其上方的实体。每种实体都有一个感知距离，并且只能感知在这个范围之内的实体。

战列舰和开采舰并不具备真实视野，这意味着他们无法分辨战列舰和开采舰。在它们的感知下，所有的开采舰都将被视为战列舰。

与此同时，实体还可以探测周围的实体，只获得它们的位置而非更加详细的信息。侦查舰有比感知范围更大的探测范围，所以它们能够探测到更远距离的实体。

### ④ 实体种类

#### 战列舰

战列舰搭载了最先进的移动模块和最强力的火力模块——这为它提供了其它兵种所没有的高机动性。战列舰将会在地图上游走，并且可以使用过载模块在行动半径内发起一次无差别的能量爆发。在发动过载模块后战列舰将会被彻底损毁。

**感知**：将会把开采舰视为战列舰。

**过载（主动能力）**：在行动范围内发起一次无差别的能量爆发（爆发的作用半径可选并且小于等于行动半径），作用范围内的所有实体将会被影响：

- 决定能量爆发后，实体的能量将立即减`10`。如果实体剩余的能量小于`10`，爆发将完全无效。

- 扣除`10`点能量后，实体剩余的能量将会被均分为`n`份，每份的能量大小记作`E`，`n`为作用半径内除实体本身的实体数量。

  - 作用半径内友方的星球将会增加`E`点能量点。

  - 作用半径内友方的其他实体将会增加`E × K`点防护值，上限为初始防护值，`K`为侦查舰的增益系数。

  - 作用半径内非友方（敌方或中立）的星球将会损失`E × K`点能量点，其他实体将会损失`E × K`点防护值，K 为侦查舰的增益系数。

- 如果能量爆发后非友方实体的防护值或能量点为负数：

  - 战列舰将会成为己方实体，防护值等于当前防护值的绝对值，上限为初始防护值。

  - 开采舰和侦查舰将会被摧毁。

  - 星球将会被转换成己方实体，能量点等于当前能量点的绝对值。

#### 开采舰

开采舰拥有独特的能源模块，这使它能够在太空中开采能量点。

**感知**：将会把开采舰视为战列舰。

**开采（被动能力）**：在被创造的`50`回合以后，开采舰将会为创造它的星球持续带来能量点收益（如果这个星球还没有易主）。假设开采舰的能量为`x`，它产生的能量点将等于`⌊(0.02 + 0.03 ⋅ e^(−0.001x)) ⋅ x⌋`。

**进化（被动能力）**：在被创造的`300`回合以后，开采舰将会进化为拥有同样能量和防护值的战列舰。

#### 侦查舰

侦查舰上搭载了强力的分析模块，是所有开采舰的天敌。侦查舰能够通过入侵直接摧毁所有的开采舰，无论开采舰的能量和防护值。

**感知**：侦查舰有比感知范围更大的探测范围，并且能够分辨出实体的真实种类。

**分析（主动能力）**：消耗`10`点防护值（防护值将不会被这个行为扣除到`0`以下），入侵行动范围内的一个开采舰，分析它的技术组成。被入侵的开采舰将会被摧毁。

通过入侵获得的技术资料将为实体友方战列舰的能量爆发提供增益。在接下来的`50`回合以内，友方战列舰将会得到一个**乘算**的能量增益，增益系数等于`(1.001)^(开采舰能量)`。如果同一时刻有复数个开采舰的增益存在，增益系数以`(1.001)^(未过期的开采舰能量之和)`计算。

#### 星球

星球可以建造其他种类的实体。星球不可被建造，亦不可被摧毁，只能通过战列舰的能量爆发来易主。初始的双方星球拥有`150`点能量点，中立星球拥有`50`到`500`点能量点。

**建造（主动能力）**：星球花费部分能量点，在相邻的、没有被其它实体占据的位置制造新的实体。

**充能**：花费一部分能量点为最终兵器充能。此行为并不会增加冷却值，也不被冷却值所限制。

每一回合开始时，每一个星球都增加一些能量点，具体数量以`E(t) = ⌈0.2 × sqrt(t)⌉`来计算，`t`为当前的回合数。

## 四、胜利

在《宙》当中，玩家的目的是赢得比赛。

每一个玩家都有最终兵器，并且将会在`1000`回合后准备完毕。每一回合，玩家的星球都会使用一部分能量点来给最终兵器充能。

每一回合使用最多能量点在充能上的星球将会产生能量共鸣，星球所属势力的最终兵器将会累计一个能量点。`1000` 回合后，拥有更多能量点的最终兵器将会彻底摧毁其余势力的部队，并且赢得比赛。

每一回合充能最多的星球将会彻底损失充能所消耗的能量点，同时其余星球仅能回收其用于充能的能量点的一半。

如果充能最多的星球有复数个，那么这些星球的最终兵器都无法获得能量点，并且都只能回收其充能的能量点的一半。

### 胜利条件

如果场上一支队伍的所有实体被全灭，它将立即失败，即使它的最终兵器拥有更多的能量点。除此之外，`1000`回合以后将会按照以下条件依次判断胜负：

- 一、最终兵器有更多的能量点。

- 二、队伍拥有更多的星球。

- 三、队伍所有实体的总能量更高。

- 四、平局。

## 五、交流

实体只能感知自己周围的信息，并且在独立的代码实例之上运行——这意味着实体之间无法共享任何变量。

唯一可以用来传递信息的方式是无线电广播。每一个实体都可以改变自身的广播内容，并且获得感知范围内所有其他实体的广播内容。改变或者感知广播内容不会增加冷却值，也不被冷却值所限制。

无线电广播的内容是一个`0`到`8`位的非负整数（即`0`-`99999999`）。

## ~六、运行时限~

~为了防止玩家的代码陷入死循环，或者占用过多资源导致比赛运行总时间过长，所有实体的运行被限制在20ms之内，超过范围的实体将会被中断运行，并且该回合不会执行任何的动作。~

## 七、其他文件

- [开发文档](/documents/)
- [可视化客户端](https://github.com/NGMAAAYO/Cosmos-Client)
