# TPMS 详细操作说明

[English](USAGE.md)

## 使用条件

- 已开启 SSH root access 的 Venus OS / GX 设备。
- 被 BlueZ 支持的 USB 蓝牙适配器。
- 会广播兼容 BLE manufacturer data 的胎压传感器。

若 GX 设置中有蓝牙开关，请保持开启。

## 安装脚本行为

脚本在修改前会显示 Venus OS 版本和 UI 档案。第一个提示输入 `n` 会直接退出，不做任何
修改。

输入 `y` 会进入 10 分钟受保护试验：临时加载 UI 和扫描服务，然后重载 GX 图形界面。在 SSH
终端输入 `CONFIRM` 后才会永久安装。输入其他内容、GUI 连续崩溃、超时或设备重启都会恢复
原 UI。

永久运行文件位于 `/data/venus-tpms-ble`，普通重启后会自动启动。Venus OS 升级会替换
`/opt` 下的 GX UI 文件，所以每次升级后必须再次运行安装命令，恢复 TPMS 菜单。

## 绑定与读数

`Discovered` 显示近期收到、尚未绑定的胎压传感器。打开传感器后选择 `Front left`、
`Front right`、`Rear left` 或 `Rear right`。

TPMS 首页只保留四个轮位、`Discover sensors` 和 `Diagnostics`。首页仅显示胎压和温度；
传感器元数据与 BLE 扫描诊断分别放在对应的二级页面。

设备列表的轮位顺序为：

```text
左前 / 右前 / 左后 / 右后
```

- `--`：未绑定传感器。
- `wait`：已绑定，但本次服务启动后尚未收到读数。
- `6.17`：当前胎压，单位 bar。
- `6.17*`：最后一次胎压，当前已过期。

未绑定传感器 5 分钟没有再次广播会从 `Discovered` 移除。已绑定轮位会跨重启保存最后一次
读数；超过新广播等待时间后标记为 `Stale`。

## 蓝牙状态

TPMS 页面会显示 `Bluetooth`、`BLE receiver`、`BLE activity (5 min)` 和
`Manufacturer data (5 min)`。

- `Bluetooth` 正常时应为 `Scanning`。
- 收到原始广播时，`BLE receiver` 应为 `Receiving`。
- 两个活动数分别是近 5 分钟实际广播的不同 BLE 设备数，以及其中带 manufacturer data 的
  设备数。它们是诊断数据，不是已配置胎压数量。

服务使用编号最小、可用的 BlueZ 适配器，不绑定特定 USB 型号或 `hci` 编号。拔出适配器后
扫描暂停，重新插入可自动恢复。部分胎压传感器广播频率低，应先靠近设备并等待几分钟再判断。

## 状态与调试

查看服务状态：

```sh
dbus-send --system --print-reply \
  --dest=com.victronenergy.tpms.main \
  /StatusText \
  com.victronenergy.BusItem.GetValue
```

正常扫描时输出：

```text
Scanning
```

需要前台调试时：

```sh
svc -d /service/venus-tpms-ble
VENUS_TPMS_DEBUG=1 python3 /data/venus-tpms-ble/venus-tpms-ble.py
```

按 `Ctrl-C` 停止后，再启动受管服务：

```sh
svc -u /service/venus-tpms-ble
```

默认不写运行日志，避免占用 GX 的有限存储空间。

## 卸载

卸载脚本会停止 TPMS、只移除自己的带标记启动项、在有备份时恢复 `PageMain.qml`、删除 TPMS
QML 页面并重载 GX 图形界面，不会修改其他启动命令。

## 开发

服务通过 D-Bus 发布 `com.victronenergy.tpms.main`。开发时可直接运行：

```sh
python3 service/venus-tpms-ble.py
```

模拟 UI 数据：

```sh
python3 tools/mock_tpms_dbus.py
```

协议解析归属 `tpms-ble-parser`；本仓库负责 Venus BLE 扫描、D-Bus 发布、UI 接入、轮位绑定、
过期状态和安装流程。
