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
	"map": "maptestsmall",  // 代表游戏运行的地图名字，地图存放在'maps/'文件夹下
	"players": [  // 代表游戏参与者的队伍名字，数量不能超过地图所规定的队伍数量。
		"example1",  // 'src/'目录下必须有相同队名的队伍代码文件夹
		"example2"
	],
	"debug": true  // 开启debug模式。在debug模式下，队伍代码抛出的错误将会中断
	               // 游戏进程，并且随机种子将会固定。保存的回放文件名称将固定为'replays-debug.rpl'
}
```

在准备好以上步骤以后，运行`main.py`或者`run.cmd`（仅在Windows环境下）即可开始游戏进程。比赛的回放文件将保存在`replays/`文件夹下。

#### 开发相关链接

- [在线对战平台](https://cosmos.misaka17032.com/)
- [可视化客户端](https://github.com/NGMAAAYO/Cosmos-Client)
