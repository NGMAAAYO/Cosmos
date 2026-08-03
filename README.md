# Cosmos - 宙

《宙》是以原生Python为引擎的实时策略游戏。在游戏当中，多名玩家将编写代码控制不同的文明相互对抗。所有玩家的目的均为彻底消灭其他竞争者，并取得最终的胜利。


- [游戏规则介绍](https://docs.misaka17032.com/)
- [游戏开发文档](https://docs.misaka17032.com/documents/)
- [新手入门指南](https://docs.misaka17032.com/brief.html)
- [从零开始设计自己的AI](https://docs.misaka17032.com/tutorial.html)

-----

#### 配置游戏

从[Releases](https://github.com/NGMAAAYO/Cosmos/releases/latest/)页面下载最新的游戏压缩包，或者[点击这里](https://github.com/NGMAAAYO/Cosmos/releases/download/v1.0.4/Cosmos.zip)下载最新版本（可能有延迟）。

解压后的文件夹即是游戏的根目录，你可以使用这个项目进行队伍代码的编写、调试，以及比赛的运行。文件夹内自带一个Windows下的Python环境，你可以直接运行`run.cmd`来开始游戏进程。

#### 配置比赛

为了运行一场比赛，你需要至少一个队伍代码。队伍代码应当是一个名为队名的文件夹，其中包含一个符合条件的、名为`main.py`的文件。将队伍代码放在`src\`下。

以下是一个名为`example`的队伍的队伍代码格式示例：

```
Cosmos
|-- src
    |-- example
        |-- main.py
        |-- ...
```

#### 运行比赛

在准备好队伍代码后，修改`config.json`中的比赛参数。

```
{
	"rounds": 1000,  // 代表游戏运行的最大总回合数
	"map": "fang",  // 代表游戏运行的地图名字，地图存放在'maps/'文件夹下
	"players": [  // 代表游戏参与者的队伍名字，数量必须等于地图所规定的队伍数量。
		"codex",  // 'src/'目录下必须有相同队名的队伍代码文件夹
		"youmu"
	],
	"debug": true,  // 开启debug模式。在debug模式下，队伍代码抛出的错误将会中断
	                // 游戏进程，并且随机种子将会固定。保存的回放文件名称将固定为'replays-debug.rpl'
	"parallel_cores": 16  // 默认请求16个决策进程；实际数量不会超过本机 CPU 核数
}
```

多进程模式会在每轮开始时生成只读状态快照，并行计算所有单位的决策，再由主进程按照该轮既定的随机顺序提交动作。相同配置与随机种子下，结果不会因 worker 的完成先后而改变。

在准备好以上步骤以后，运行`main.py`或者`run.cmd`（仅在Windows环境下）即可开始游戏进程。比赛的回放文件将保存在`replays/`文件夹下。

#### 竞赛数值与地图

正式比赛固定为`1000`回合。开采舰从第`50`龄到第`300`龄获得收益；令舰龄为`a`、能量为`E`、`n(a) = clamp(a - 49, 0, 251)`，累计收益为`M(E,a) = floor(n(a)E / 300)`，当回合收益为`M(E,a) - M(E,a-1)`。因此完整生命周期收益严格小于本金，不会形成自我维持的指数经济。

侦查舰在最近`50`回合内分析的敌方开采舰能量总和记为`S`，友方过载增益为`K(S) = 2^(min(S,1000)/1000)`，最高为`2`倍。

内置的六张确定性竞技地图不使用随机生成器；自然以太由对称谐波花纹生成，`0.0001`以太格是会令进入者长期失去行动能力的黑洞隔断。

| 类型 | 小/单星球 | 大/多星球 | 目标 |
|:--:|:--:|:--:|:--|
| 决斗 | `Fang` | `Bastion` | 无中立星球，直接攻防 |
| 中心 | `Crown` | `Crucible` | 唯一`75`能量中心星球 |
| 分路 | `Fork` | `Delta` | 两颗镜像`100`能量星球 |

地图的详细数值、路线和再生成方法见[`maps/README.md`](maps/README.md)。运行`python utils/designed_maps.py`可以确定性地重建六张地图。

#### 开发相关链接

- [在线对战平台](https://cosmos.misaka17032.com/)
- [可视化客户端](https://github.com/NGMAAAYO/Cosmos-Client)
