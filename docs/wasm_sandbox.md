# WebAssembly 玩家沙箱

WebAssembly 模式把玩家提交的 `main.py` 当作一种受限的 Python 语法语言。源码只会经过 `ast.parse` 和静态编译，不会被 CPython `import`、`exec` 或 `eval`。

## 启用方式

先安装依赖：

```bash
python -m pip install -r requirements.txt
```

Wasm 是默认玩家运行时。可以在 `config.json` 中显式设置预算：

```json
{
  "player_runtime": "wasm",
  "wasm_fuel": 100000,
  "wasm_host_calls": 10000,
  "wasm_max_sensed": 4096,
  "sandbox_seed": 0
}
```

- `wasm_fuel` 是每个实体每回合可消耗的确定性 Wasm 指令预算。
- `wasm_host_calls` 限制每回合调用游戏 API 的次数，因为宿主函数执行时间不计入 Wasm fuel。
- `wasm_max_sensed` 限制一个实体的只读感知快照大小。
- `sandbox_seed` 用于派生每实体独立、可重放的 `random_int()` 随机序列。

任一预算耗尽、Wasm trap 或非法 API 调用都会终止当前实体的本回合运行。Controller 副本、Wasm 私有 globals 和私有 RNG 都不会提交；其他实体继续运行。

`player_runtime: "python"` 保留给本地兼容调试，并且必须显式启用。它会直接导入玩家模块，不是安全模式，不应在非受信比赛中使用。

## 源码格式

```python
from core.api import *


class Player:
    def __init__(self):
        self.turns = 0

    def run(self, controller):
        self.turns += 1

        if controller.get_type() == EntityType("planet"):
            if controller.can_charge(1):
                controller.charge(1)
            return

        if not controller.is_ready():
            return

        for entity in controller.sense_nearby_entities(
            teams=controller.get_opponent()
        ):
            direction = controller.get_location().direction_to(entity.location)
            if controller.can_move(direction):
                controller.move(direction)
                return
```

也可以定义不带额外参数的 `run_planet`、`run_destroyer`、`run_miner` 和 `run_scout`；没有 `run` 时编译器会生成类型分发。`self` 字段必须在 `__init__` 中以常量声明，它们会编译成每个实体实例私有的 Wasm global。

## 支持的语言子集

- 有符号 64 位整数、布尔值、`None` 哨兵；算术溢出按 i64 回绕。
- 局部变量和 `self` 私有字段。
- `if`、`while`、`break`、`continue`、`return`。
- `for ... in range(...)`、方向列表和 `sense_nearby_entities(...)`。
- 非递归的类内 helper 方法。
- `abs`、双参数 `min/max`、`int/bool`。
- `Direction`、`MapLocation`、`EntityType`、`Team` 的整数属性和常用方法。
- Controller 的整数/布尔查询、移动、建造、充能、过载、分析和无线电 API。
- `controller.random_int(limit)`：每实体独立的确定性随机数，不读取或修改 Python 全局随机状态。

当前版本不支持浮点数，所以 `sense_aether()`、浮点冷却属性和 `get_overdrive_factor()` 尚未开放。`sense_entity()`/`detect_nearby_entities()` 的可选对象返回值也尚未开放；请使用 `sense_nearby_entities()` 循环。

## 明确禁止

- 除声明用途的 `from core.api import *`、`from src import template` 之外的所有 import。
- 模块全局变量、类变量、`global`、`nonlocal`。
- `eval`、`exec`、`compile`、`open`、`getattr` 等任意动态调用。
- 文件、网络、子进程、线程、`ctypes`、GC、frame、traceback、反射和 Python 全局 RNG。
- 动态类、装饰器、元类、描述符、异常处理、生成器和协程。
- 递归 helper、动态属性、动态函数调用。

生成的 Wasm 模块只导入它实际使用的 `cosmos.*` 标量函数，不启用 WASI，不包含线性内存、table、共享内存或线程。每个实体拥有独立的 Wasmtime `Store/Instance`，因此模块变量或类变量无法成为实体间的隐蔽通信通道；唯一可观察的跨实体信息仍是引擎提供的感知快照和无线电。
