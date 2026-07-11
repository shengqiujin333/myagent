Now I have all the information needed. Let me write the context.md.

```markdown
# Build Context

## Goal

完成电池内阻测量系统的固件设计。基于 STM32G030F6P6 (TSSOP-20) MCU，实现交流注入法电池内阻测量，支持 DS18B20 温度测量、UART 级联多机通讯（主/从机自动识别）、定时测量（1 分钟间隔）。整体采用状态机架构，禁止阻塞。输出到 `battery_re/` 工程目录，用 Keil MDK (ArmClang V6.19) 编译通过。

## Source Materials

### Directory Overview

| Directory | Summary |
|-----------|---------|
| `battery_re/` | 目标工程目录，包含 Core/Drivers/MDK-ARM 三个子目录 |
| `battery_re/Core/` | 应用层源文件（Src/Inc），当前仅有 stm32g0xx_it.c/system_stm32g0xx.c 及 stm32g0xx_hal_conf.h/stm32g0xx_it.h |
| `battery_re/Drivers/` | STM32G0xx_HAL_Driver（HAL/LL 驱动源文件）和 CMSIS（ARM CMSIS 5.9.0，含 DSP 库 arm_cortexM0l_math.lib） |
| `battery_re/MDK-ARM/` | Keil 工程文件 battery_re.uvprojx，启动文件 startup_stm32g030xx.s，构建日志 |
| `.document-reader/` | 硬件文档的 Markdown 转换结果：网表(netlist)、BOM、DS12991 数据手册 |
| `.understand-anything/` | 项目理解中间文件（JSON 格式），含 import-map/structure 分析 |
| `Netlist_Schematic1_2026-05-25.tel` | 原始网表文件（.tel 格式） |
| `user_req.txt` | 用户需求描述 |

### Key Files Inspected

- `user_req.txt` — 核心需求文档：19 条功能要求 + 8 条实现步骤
- `Netlist_Schematic1_2026-05-25.tel` — 完整网表，含 MCU 引脚连接、所有信号网络
- `.document-reader/netlist/document.md` — 网表 Markdown 转换（同原始 tel 内容）
- `.document-reader/BOM/document.md` — BOM 表：46 行物料清单
- `.document-reader/BOM_Board1_Schematic1_2026-05-23/document.md` — Board1 专用 BOM
- `.document-reader/DS12991/chunks/chunk_0034~chunk_0040.md` — DS12991 数据手册第 4 章引脚分配表（TSSOP20 引脚图 + Table 12）
- `.document-reader/DS12991/summary.json` — DS12991 摘要：STM32G030x6/x8 系列，Cortex-M0+，最高 64MHz
- `battery_re/MDK-ARM/battery_re.uvprojx` — Keil 工程配置：MCU=STM32G030F6Px，Flash 64KB, RAM 8KB，编译选项 ArmClang V6.19
- `battery_re/MDK-ARM/battery_re.BAT` — 批处理构建脚本，展示完整编译命令链
- `battery_re/MDK-ARM/build_log.txt` — 上一次成功构建日志（0 Error, 0 Warning）
- `battery_re/Core/Src/system_stm32g0xx.c` — 系统初始化：HSE 8MHz → PLL (×16, /2) → SysClk 64MHz，Flash 2 WS
- `battery_re/Core/Src/stm32g0xx_it.c` — 中断服务框架：声明了 hadc1, htim3, htim14, hdma_adc1, huart1, huart2 等外部句柄；定义了 SCHED_IncTick/UART_IRQHandler 弱符号桩
- `battery_re/Core/Inc/stm32g0xx_hal_conf.h` — HAL 模块使能：ADC, TIM, UART, DMA, GPIO, EXTI, IWDG, PWR, FLASH, RCC, CORTEX
- `__ds12991_tmp.txt` — DS12991 数据手册临时提取文本
- `__out1.txt` — DS12991 数据手册临时提取文本（重复）

## Task Requirements

### Functional behavior
- MCU 产生 1kHz 占空比 50% 的 PWM 方波（TIM3_CH3），经 RC 滤波 → 正弦波 → 跟随器 → 运放恒流，向电池注入交流电流
- 测量电池两端产生的电压（VOLT_ADC）和注入电流（CURRENT_ADC），计算电池内阻
- 每 1 分钟定时测量一次
- DS18B20 温度测量（DQ 引脚），每 30 秒测量一次
- UART2 作为从机接收前级主机指令；UART1 作为主机与后级从机通讯
- 主机可给从机分配地址，主机轮询读取所有从机的数据（电压、电流、内阻、温度等）
- MCU Pin12 (M_S) 判断主/从：上拉后检测电平，高电平为主机，低电平为从机；开机判断一次后改输入（省电）
- 整体禁止阻塞，全部用状态机实现
- 注入电流和电压采样需同步（10kHz 采样率），对 RC 电路引入的相位差进行校准
- 使用实际电阻对测量进行多点校准
- 异常数据识别算法（抗充电/放电逆变器干扰）

### Interfaces and protocols
- UART1：主机模式，与后级从机通讯，自定义协议
- UART2：从机模式，接收前级主机指令，自定义协议
- DS18B20：单总线协议（DQ）
- UART 级联协议需自定义，主机分配地址、轮询读取所有从机数据

### Outputs and indicators
- 测量结果通过 UART 级联网络上报至主机
- [推断] 暂无独立显示或指示灯硬件

### Timing and performance
- 1kHz PWM 注入频率（50% 占空比）
- 10kHz ADC 采样率（与电流注入同步）
- 1 分钟定时测量周期
- DS18B20 30 秒测量间隔

### Tests and acceptance criteria
- 通过 Keil 编译（0 Error, 0 Warning）
- 硬件测试命令未提供，[推断] 通过串口观察数据上报

## Hardware Connection

### MCU / SoC
- Part number: STM32G030F6P6TR
- Core / architecture: ARM Cortex-M0+, 32-bit, up to 64 MHz
- Package: TSSOP-20 (6.5×4.4 mm, 0.65 mm pitch)
- Flash: 64 KB, SRAM: 8 KB
- Datasheet: DS12991 Rev 6

### Debug / Flash Interface
- Protocol: SWD (Serial Wire Debug)
- Connector: H5 (HDR-TH_4P-P2.54-V-M, 4-pin header, 2.54mm pitch)
  - H5.1: 3.3V
  - H5.2: ISOGND
  - H5.3: SWDIO (PA13, MCU pin 18)
  - H5.4: SWCLK (PA14, MCU pin 19)
- Required tools: J-Link / ST-Link / pyOCD

### Peripheral Wiring

| Signal | MCU U3-1 Pin | TSSOP20 Pin | MCU GPIO | Target Device / Module | Direction | Notes |
|--------|-------------|-------------|----------|----------------------|-----------|-------|
| UART1_RX | U3-1.1 | 1 | PB7 (AF0) | UART 级联（从机 RX 来自前级 TX） | IN | R11 (10Ω) 串联 |
| CN3.1 | U3-1.2 | 2 | - | CN3.1 (UART 联接头), U5.1 (CA-IS3721LS 隔离器输入) | IN/OUT | 经隔离器通讯 |
| VDD | U3-1.4 | 4 | - | 3.3V 供电 | PWR | XC6206P332MR-G LDO 输出 |
| VSS | U3-1.5 | 5 | - | ISOGND | PWR | 隔离地 |
| NRST | U3-1.6 | 6 | NRST | U6.1 (滤波电容) | IN | 外部复位 |
| VSS | U3-1.7 | 7 | - | ISOGND | PWR | 隔离地 |
| VOLT_ADC | U3-1.8 | 8 | PA1 (ADC_IN1) | 电池电压分压采样 | IN | 分压 R4-1/R5-1 (100k/100k), C5-1 滤波 |
| UART2_TX | U3-1.9 | 9 | PA2 (AF1/USART2_TX) | 隔离器 U5.6 (CA-IS3721LS) | OUT | R8 (10Ω) 串联 |
| UART2_RX | U3-1.10 | 10 | PA3 (AF1/USART2_RX) | 隔离器 U5.7 (CA-IS3721LS) | IN | R7 (10Ω) 串联 |
| DQ | U3-1.11 | 11 | PA4 | H6.2 (DS18B20 数据), R6 (4.7kΩ 上拉至 3.3V) | IN/OUT | 单总线 |
| M_S | U3-1.12 | 12 | PA5 | R9 (100kΩ 上拉至 3.3V) | IN | 主/从选择，开机读电平 |
| CURRENT_ADC | U3-1.13 | 13 | PA6 (ADC_IN6) | U11 运放输出 (电流检测) | IN | R52 (100kΩ) 连接 U11.1 |
| RES_ADC | U3-1.14 | 14 | PA7 (ADC_IN7) | U10.7 运放输出 (内阻电压检测) | IN | C24 (1nF) + R38 (10kΩ) 滤波 |
| TIM3_CH3 | U3-1.15 | 15 | PB0 (AF1/TIM3_CH3) | R21 (100kΩ) 至 RC 滤波网络 | OUT | 1kHz 50% 方波 → 正弦波生成 |
| SWDIO | U3-1.18 | 18 | PA13 | H5.3 (SWD 调试口) | IN/OUT | SWD 数据 |
| SWCLK | U3-1.19 | 19 | PA14 | H5.4 (SWD 调试口) | IN | SWD 时钟 |
| UART1_TX | U3-1.20 | 20 | PB6 (AF0/USART1_TX) | UART 级联（主机 TX 通往后级从机） | OUT | R10 (10Ω) 串联 |

[推断] U3-1.3 (Pin 3, PC15-OSC32_OUT) 和 U3-1.16/17 未在网表中出现，可能悬空或用于板级调试未标注。

### Power
- Supply voltage: 外部 +12V 输入 (CN1/CN2 2-pin 3.96mm 连接器)
- LDO: XC6206P332MR-G (U2-1) — 3.3V 输出，SOT-23-3 封装
  - 输入: 5V → 输出: 3.3V (给 MCU 及数字电路供电)
  - 另有 3.3VA (模拟供电) 和 5VA (模拟 5V) 电源网络
- 隔离电源: VPS8701B (U1-1) + VPT87DFB01B (T1-1) 组成的隔离 DC-DC 转换器
  - 输入: +12V
  - 输出: 隔离侧 5V/3.3V (ISOGND 参考)
- 基准电压: 1.65V 网络，由 TLV431AIDBZR (U1) 通过 R4/R5 分压产生
- 电源保护: SMAJ15CA TVS(D1-1), 0603L050YR PTC(F1-1), RB160M-30 Schottky(D2-1/D3-1)

## Uncertainties

- U3-1.3 (TSSOP20 Pin 3 = PC15-OSC32_OUT) 未在网表中出现连接，[推断] 可能悬空或作为 GPIO 未标注
- U3-1.16/Pin 16 和 U3-1.17/Pin 17 在网表中未出现，[推断] 悬空
- U8/U9/U10/U11 (SOP-8 封装) 的具体型号未在 BOM 中标注，[推断] 可能为通用运放（如 LMV321 等）
- RC 滤波电路的具体截止频率未标注（C4~C7/C11~C14 1nF + R18~R21 100kΩ，[推断] 约 1.6kHz 低通）
- 相位差校准算法细节和异常数据识别算法需自行设计
- 多点校准方法需自行设计（使用实际电阻）
- UART 级联协议需完全自定义

## Build, Flash, And Run Notes

- **Build system**: Keil MDK (µVision V5), ArmClang V6.19
- **Build command**: `C:\Keil_v5\UV4\UV4.exe -j0 -b "MDK-ARM/battery_re.uvprojx" -o "MDK-ARM/build_log.txt"`
  - `-j0` 抑制弹窗，`-b` 增量编译，`-o` 日志输出
  - 退出码: 0 成功, 1 仅警告, 2+ 错误, 21+ 致命错误
- **Project file**: `battery_re/MDK-ARM/battery_re.uvprojx`
- **Working directory**: `C:\Users\123\Desktop\neizu\tasknew\battery_re`
- **Output artifacts**: `battery_re/battery_re.axf` (ELF), `battery_re/battery_re.hex` (Intel HEX)
- **Flash command (参考)**: `pyocd flash -t stm32f103c8 build/firmware.elf` （但 MCU 为 STM32G030，命令需改为 `-t stm32g030f6`）
- **Serial debug**: COM3, 115200 baud, 8N1 (硬件配置给出)
- **Host test**: `python host_tests/smoke_test.py --port COM7 --baud 115200`
- **Required defines**: `USE_HAL_DRIVER`, `STM32G030xx`
- **Include paths**:
  - `../Core/Inc`
  - `../Drivers/STM32G0xx_HAL_Driver/Inc`
  - `../Drivers/STM32G0xx_HAL_Driver/Inc/Legacy`
  - `../Drivers/CMSIS/Device/ST/STM32G0xx/Include`
  - `../Drivers/CMSIS/Include`
  - `..\Drivers\CMSIS\DSP\Include`
- **Linker**: 无分散加载文件（ScatterFile 留空），使用默认链接脚本
- **Memory**: Flash 0x08000000 (64KB), RAM 0x20000000 (8KB)
- **已存在的源文件需保留的**:
  - `Core/Src/system_stm32g0xx.c`（系统时钟初始化 64MHz）
  - `Core/Src/stm32g0xx_it.c`（中断框架，含弱符号桩）
  - `Core/Inc/stm32g0xx_hal_conf.h`（HAL 配置）
  - `Core/Inc/stm32g0xx_it.h`（中断声明）
  - `MDK-ARM/startup_stm32g030xx.s`（启动文件，Stack 1KB, Heap 512B）
- **需创建的源文件**:
  - `Core/Src/main.c`（主入口，含 Error_Handler、MX_* 初始化函数）
  - `Core/Src/stm32g0xx_hal_msp.c`（HAL MSP 初始化）
  - 以及应用模块文件（状态机、UART 驱动、ADC 采集、DS18B20、PWM 生成、通讯协议等）

## Constraints And Risks

- **Missing information**: U3-1.3/16/17 引脚连接不明；U8~U11 具体型号未知
- **Unclear hardware details**: RC 滤波级数/截止频率需从原理图反推；电流恒流源具体增益未知
- **Uncertain build or flash commands**: 硬件配置给出的 flash 命令是 stm32f103c8，需改为 stm32g030f6
- **Incomplete acceptance criteria**: 无明确验收测试用例；无 BSP/板级支持包
- **Truncated or unreadable files**: DS12991 PDF 转 Markdown 格式混乱，引脚表需交叉验证
- **Real-hardware verification risks**: 未知电路板的实际运行状态；电源/隔离电路首次上电风险

## Confidence Assessment

| Section | Confidence | Reason |
|---------|-----------|--------|
| Goal | High | 用户需求清晰明确，目标具体 |
| Task Requirements | High | 19 条要求无歧义，覆盖功能/协议/时序/架构 |
| Hardware Connection | Medium | 网表完整，但 MCU 部分引脚不明，U8~U11 型号未知 |
| Build & Flash | High | Keil 工程完整，构建已验证成功 |
| Constraints & Risks | Medium | 硬件不确定性 + 无验收测试 + 协议需自定义 |
```