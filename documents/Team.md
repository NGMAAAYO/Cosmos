## Team

[Team](https://github.com/NGMAAAYO/Cosmos/blob/9a101853691e34b9c8d3f7b109fbe916e227326b/core/api.py#L217) 类定义了队伍的基本概念。

构造方法：core.api.Team(tag)  
- tag (str): 团队名称，例如 "a"、"b" 或 "Neutral"  

### 方法

#### def is_player(self) -> bool
> 判断当前团队是否由玩家控制。  
> 返回：  
> - bool: 如果团队为玩家控制，则返回 True；否则返回 False。

#### def __eq__(self, other: Union[Team, str]) -> bool
> 判断当前团队是否与另一个团队相同。
> 参数：
> - other (Union[Team, str]): 另一个团队实例或团队名称。
> 返回：
> - bool: 如果两个团队相同，则返回 True；否则返回 False。
