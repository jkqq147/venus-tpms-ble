# venus-tpms-ble 中文说明

在 Victron Venus OS / GX 设备上显示 BLE 胎压数据。安装后，GX 设备列表会出现
`TPMS` 页面，可扫描传感器并绑定左前、右前、左后、右后四个轮位。

运行时采用静态原生 Rust 服务。

## Dashboard

![GX 设备上的 TPMS Dashboard](docs/images/dashboard.png)

## TPMS 页面

![TPMS 轮位、传感器扫描与诊断页面](docs/images/tpms-page.png)

[English](README.md) | [详细操作说明](docs/USAGE.zh-CN.md)

## 已验证环境

已在 Color Control GX（`armv7`）的 Venus OS `v3.55` 上验证。其他版本尚未验证；
安装器在任何版本上都会先进入受保护试验，再允许永久安装。

## 安装

先按 [Victron 官方文档开启 SSH / root access](https://www.victronenergy.com/live/ccgx:root_access)，
SSH 登录 GX 后运行：

```sh
wget -O - https://raw.githubusercontent.com/jkqq147/venus-tpms-ble/master/install.sh | sh
```

脚本会先启动临时试验并重载 GX 图形界面。确认 GX 本机 `TPMS` 页面正常后，在 SSH
终端输入 `CONFIRM` 才会永久安装；输入其他内容会恢复原 UI。

## 使用

1. 在 GX 设备列表打开 `TPMS`。
2. 等待 `Discovered` 出现传感器。
3. 打开传感器并设置 `Wheel` 轮位。

## 重启与升级

普通重启后 TPMS 会自动启动。**每次 Venus OS 升级后**，都必须重新运行上方安装命令并
完成试验确认，因为系统升级会替换提供 TPMS 菜单的 GX UI 文件。

## 卸载

```sh
wget -O - https://raw.githubusercontent.com/jkqq147/venus-tpms-ble/master/uninstall.sh | sh
```

显示含义、蓝牙状态、排障和开发说明请见[详细操作说明](docs/USAGE.zh-CN.md)。
