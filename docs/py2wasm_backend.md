# py2wasm AOT 后端

此实验后端固定使用 `wasmerio/py2wasm` 的 `wasi` 分支提交
`07da21cac92f5e5967c4bb5d39aaabaee1c70b3e`。它通过 Nuitka 把玩家 Python
编译成 C，再使用 WASI SDK 21 和静态 `libpython.a` 生成 Wasm。游戏通过
Wasmtime fuel 中断超时单位，并且只向 guest 提供标量 `cosmos.call` 与
`cosmos.call_float` 能力。

## 准备编译器

编译器要求 Python 3.11。完整 checkout、WASI SDK 和预编译 Python 超过 500 MB，
因此不提交到 Git：

```bash
python tools/setup_py2wasm.py --python /path/to/python3.11
export COSMOS_PY2WASM_ROOT="$PWD/.cache/py2wasm"
export COSMOS_PY2WASM_PYTHON="$PWD/.cache/py2wasm/.venv/bin/python"
```

安装脚本固定并应用两份可审计补丁：

1. 不把宿主 Python 的 `MODLIBS`（Linux 常包含 WASI 不提供的 `libatomic.a`）
   传给 wasm32-wasi 链接器；
2. 内建 `_cosmos`、保持 CPython 初始化状态、导出 `cosmos_turn`，并关闭
   `export-dynamic`，使正式产物仅导出 `memory`、`_start`、`cosmos_turn`。

## 使用方式

配置 `player_runtime` 为 `py2wasm`。此后端使用独立的 Wasm fuel 预算，默认给当前
合格策略保留了大幅余量：

```json
{
  "player_runtime": "py2wasm",
  "py2wasm_fuel": 100000000,
  "wasm_host_calls": 200000,
  "wasm_max_sensed": 16384
}
```

Python 源码产物和 Wasmtime 本机 AOT 产物分别缓存在
`.cache/cosmos-py2wasm-artifacts/`。Cranelift 在一次性子进程中运行；比赛进程只
反序列化按 Wasm digest、Wasmtime 版本、CPU 架构和内存/栈配置区分的可信缓存，
避免把约 1–2 GB 的并行编译工作集永久留在服务器进程。

## 隔离和资源语义

- 所有团队 import 使用正向白名单；`os`、文件、网络、子进程、`ctypes`、反射、
  调用栈及动态执行入口在编译前拒绝。
- 每个实体拥有独立 Store、线性内存、CPython 模块图、类变量、模块全局变量和
  RNG；因此不能借共享 Python 状态绕过无线电规则。
- 旧策略的 `random` 会透明改写到宿主提供的每实体确定性 RNG；不会接触服务器
  Python 的全局 RNG。
- Store 限制为 64 MiB 内存、2 MiB Wasm 栈；默认每回合 1 亿 fuel、20 万宿主
  调用。当前六支 `src` 策略都通过源码策略并完成真实 AOT 编译/初始化。
- Controller 是事务副本。fuel、宿主调用或异常预算失败时，游戏丢弃全部动作；
  被 Wasm trap 中断的 CPython 堆不能安全续跑，因此该实体 guest 重置到刚创建的
  可信模板，外部表现仍是本回合什么都不做。
- py2wasm 上游的装饰器问题
  [#13](https://github.com/wasmerio/py2wasm/issues/13) 会令 CPython 内建
  `staticmethod/property` 触发间接调用签名错误。可信 guest 层提供等价纯 Python
  描述符，玩家无需修改源码。

## 2026-08-03 实测结论

`codex` 首次编译约 33.5 秒、27,520,988 字节；`youmu` 约 51.3 秒、
29,176,219 字节。两者初始内存均为 151 页，产物只有 3 个导出。源码缓存命中后
验证约为毫秒级；本机 AOT 缓存命中后双队初始化约 0.3–0.4 秒。

同一地图、随机种子和 `youmu vs codex` 1000 回合轨迹下：

| 后端 | 比赛用时 | 峰值实体 | 峰值 RSS | 超限 |
|---|---:|---:|---:|---:|
| 原生 Python | 30.60 秒 | 231 | 124.5 MiB | 不适用 |
| py2wasm | 1010.41 秒 | 231 | 3098.5 MiB | 0 |

当前 py2wasm 比原生 Python 慢约 33.0 倍、峰值 RSS 高约 24.9 倍。移除每回合完整
内存快照后，剩余主成本是每实体约 12–13 MiB 的独立嵌入式 CPython，以及在 Wasm
中执行 CPython/Nuitka 代码和跨 ABI 调用。也就是说，它已经实现强隔离、确定性
超时和 AOT 分发，但没有实现本项目最初希望的比赛性能提升；在解决每实体 CPython
实例成本之前，不应替换默认 `wasm` 后端。
