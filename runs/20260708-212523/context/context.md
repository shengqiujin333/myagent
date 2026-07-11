```markdown
# Build Context

## Goal

基于 STM32G030F6P6 (TSSOP-20) MCU，重构 battery_re 项目固件，实现电池内阻测量系统。核心功能：

- MCU 产生 1kHz 占空比 50% 矩形波 → RC 滤波成正弦波 → 运放恒流注入电池
- 采样电阻 100mΩ，采集电池两端电压和注入电流，计算电池内阻
- 每 1 分钟测量一次内阻
- DS18B20 温度传感器，每 30s 测量一次温度
- UART1 级联（多电池手拉手通讯），主机通过 UART1 给从机分配地址并轮询数据
- UART2 作为从机接收前面主机的指令
- M/S (Master/Slave) 引脚上电判断主机/从机角色
- 全部使用状态机，禁止阻塞
- 10kHz ADC 采样与电流相位同步，含相位校准和多点电阻校准
- 异常数据识别算法（抗充放电干扰）
- 使用 Keil MDK (ARMCLANG V6.19) 编译

## Source Materials

### Directory Overview

| Directory | Summary |
|-----------|---------|
| `battery_re/Core/Inc/` | HAL 配置头文件 (`stm32g0xx_hal_conf.h`) 和中断头文件 |
| `battery_re/Core/Src/` | 已有 `stm32g0xx_it.c`（中断处理骨架）、`system_stm32g0xx.c`（时钟配置 64MHz） |
| `battery_re/Drivers/STM32G0xx_HAL_Driver/` | STM32G0 HAL 驱动库（ADC、UART、TIM、DMA、GPIO、RCC 等） |
| `battery_re/Drivers/CMSIS/` | CMSIS 核心和 DSP 库 (`arm_cortexM0l_math.lib`) |
| `battery_re/MDK-ARM/` | Keil 项目文件 (`battery_re.uvprojx`)、启动文件、链接脚本 |
| `.document-reader/DS12991/` | STM32G030x6/x8 数据手册（PDF 转换的 Markdown 分片） |
| `.document-reader/netlist/` | 网表文件 (Tel 格式转 Markdown) |
| `.document-reader/BOM_Board1_Schematic1_2026-05-23/` | BOM 清单 |

### Key Files Inspected

- `user_req.txt` — 完整的用户需求文档。描述了功能目标、引脚分配、通讯协议要求、状态机设计等全部需求。
- `Netlist_Schematic1_2026-05-25.tel` — 原始网表文件，包含所有元器件的网络连接关系。
- `.document-reader/netlist/document.md` — 网表文件的 Markdown 渲染版本，列出了电源网络、信号网络和各器件引脚连接。
- `.document-reader/BOM_Board1_Schematic1_2026-05-23/document.md` — BOM 清单。关键元器件：MCU STM32G030F6P6TR、隔离芯片 CA-IS3721LS、运放 LM258DT、LDO XC6206P332MR-G (3.3V)、MOSFET SS8050、采样电阻 0.1Ω、变压器 VPT87DFB01B 等。
- `.document-reader/DS12991/chunks/chunk_0034.md` 至 `chunk_0042.md` — 数据手册的引脚排列图和引脚分配表（含 TSSOP-20 封装映射）。
- `battery_re/Core/Inc/stm32g0xx_hal_conf.h` — HAL 模块配置：使能了 ADC、IWDG、TIM、UART、GPIO、EXTI、DMA、RCC、FLASH、PWR、CORTEX。
- `battery_re/Core/Src/system_stm32g0xx.c` — 系统初始化：HSE 8MHz → PLL ×16 ÷2 = 64MHz 系统时钟，Flash 2 等待周期。
- `battery_re/Core/Src/stm32g0xx_it.c` — 中断服务例程骨架，包含 SysTick、DMA1_Ch1、ADC1、TIM3、TIM14、TIM1_BRK_UP、USART1/2 的中断处理，并定义了 `SCHED_IncTick()` 和 `UART_IRQHandler()` 弱符号。
- `battery_re/MDK-ARM/battery_re.uvprojx` — Keil 项目文件。设备 STM32G030F6Px，ARMCLANG V6.19，输出 HEX。项目分组：Application/MDK-ARM (startup)、Application/User/Core (main.c, stm32g0xx_it.c, stm32g0xx_hal_msp.c)、Drivers/STM32G0xx_HAL_Driver (22 个 HAL 源文件)、Drivers/CMSIS (system_stm32g0xx.c, arm_cortexM0l_math.lib)。
- `battery_re/MDK-ARM/battery_re.sct` — 链接脚本：IROM 0x08000000 (64KB)，IRAM 0x20000000 (8KB)。
- `battery_re/MDK-ARM/build_log.txt` — 最后一次成功构建日志（0 Error, 0 Warning），Program Size: Code=3432 RO-data=288 RW-data=12 ZI-data=1660。
- `battery_re/MDK-ARM/battery_re_build_gs.log` — 失败的重新构建日志（1 Error）：`BOARD_PIN_PWM_AF` 宏 `GPIO_AF2_TIM3` 未定义。

### 缺失文件

- **`Core/Src/main.c`** — 在 uvprojx 中引用但文件已被删除（有残留的 `main.o`）。需要重建。
- **`Core/Src/stm32g0xx_hal_msp.c`** — 在 uvprojx 中引用但文件已被删除（有残留的 `stm32g0xx_hal_msp.o`）。需要重建。
- **`Core/Inc/main.h`** — 包含了 `BOARD_PIN_PWM_AF` 等板级宏定义，已被删除。需要重建。

## Task Requirements

### 功能行为
- MCU 产生 1kHz、50% 占空比的 PWM 矩形波 → 外部 RC 滤波成正弦波 → 恒流注入电池
- 采集采样电阻 (100mΩ) 两端电压得注入电流，采集电池两端电压 → 计算内阻
- 每 1 分钟自动测量一次内阻
- DS18B20 温度传感器（DQ 引脚）每 30s 读取一次温度
- UART1 级联：主机轮询所有从机数据（电压、电流、内阻、温度等）
- UART2 作为从机接收主机命令
- 上电时检测 Pin12 (M_S) 电平判断主机/从机（内部上拉输入，检测后改输入省电）
- 全部使用状态机，禁止阻塞
- 10kHz ADC 采样与电流相位同步
- 校准：电流-电压相位差校准 + 多点电阻校准
- 异常数据识别算法

### 接口和协议
- UART1（PB6 TX / PB7 RX）：级联通讯，自定义协议，主机分配地址、轮询数据
- UART2（PA2 TX / PA3 RX）：从机接收前级命令
- 单总线 DQ (PA4)：DS18B20 温度传感器
- M_S (PA5)：主机/从机判断，高电平=主机，低电平=从机
- SWD (PA13 SWDIO, PA14 SWCLK)：调试烧录

### 输出和指示
- TIM3_CH3 (PB0) PWM 1kHz 50% 方波输出
- 电池注入电流通过采样电阻 100mΩ 测量
- 无板载 LED（PCB 无 LED 相关元器件）

### 定时和性能
- ADC 采样率 10kHz（100μs 周期），与 PWM 相位同步
- 系统时钟 64MHz
- 主测量周期：1 分钟
- 温度读取周期：30s

### 测试和验收
- 编译通过（Keil UV4, 0 Error 0 Warning）
- 主机/从机通讯正常
- 内阻测量精度满足校准后多点匹配
- 异常数据不被采用

## Hardware Connection

### MCU / SoC
- **型号**: STM32G030F6P6TR
- **核心**: ARM Cortex-M0+, 64MHz
- **封装**: TSSOP-20 (6.4×4.4mm)
- **Flash**: 32KB, **SRAM**: 8KB
- **数据手册**: DS12991 Rev 6

### 调试/烧录接口
- **协议**: SWD (Serial Wire Debug)
- **连接器**: H5 (HDR-TH_4P-P2.54-V-M, 4-pin排针)
- **引脚**: Pin1=3.3V, Pin2=GND(ISOGND), Pin3=SWDIO(PA13), Pin4=SWCLK(PA14-BOOT0)
- **工具**: pyocd flash -t stm32f103c8（硬件配置中给定，实际应使用 STLink 或 JLink 通过 SWD 烧录）

### 外设接线

| 信号 | MCU引脚 (TSSOP20#) | 目标器件/模块 | 方向 | 说明 |
|------|-------------------|--------------|------|------|
| UART1_TX | PB6 (Pin20) | CN4.2 → R10(10Ω) → UART级联总线 | OUT | 级联主机发送 |
| UART1_RX | PB7 (Pin1) | CN4.3 → R11(10Ω) → UART级联总线 | IN | 级联主机接收 |
| UART2_TX | PA2 (Pin9) | U5.6 (CA-IS3721LS) Ch.B OUT → CN3.2 | OUT | 隔离UART发送 |
| UART2_RX | PA3 (Pin10) | U5.7 (CA-IS3721LS) Ch.B IN ← CN3.1 | IN | 隔离UART接收 |
| DQ | PA4 (Pin11) | H6.2 → R6(4.7kΩ上拉3.3V) → DS18B20数据线 | I/O | 单总线温度传感器 |
| M_S | PA5 (Pin12) | R9(100K上拉3.3V) → M_S信号 | IN | 主机/从机选择，高=主机 |
| TIM3_CH3 (PWM) | PB0 (Pin15) | R21(100K) → RC滤波网络 | OUT | 1kHz/50%方波→正弦波 |
| VOLT_ADC | PA1 (Pin8) | 分压网络(R4-1,R5-1) → 电池电压分压 | IN | ADC_IN1，测量电池电压 |
| CURRENT_ADC | PA6 (Pin13) | R52(100kΩ) → U11运放输出 | IN | ADC_IN6，测量注入电流 |
| RES_ADC | PA7 (Pin14) | R38(10kΩ) → U10运放输出 | IN | ADC_IN7，测量电阻电压 |
| NRST | NRST (Pin6) | U6.1 (复位IC?) + R? | IN | 外部复位 |
| SWDIO | PA13 (Pin18) | H5.3 | I/O | SWD数据线 |
| SWCLK | PA14-BOOT0 (Pin19) | H5.4 | IN | SWD时钟线 |
| PC14 | PC14 (Pin2) | CN3.1 → U5.1 (CA-IS3721LS) | I/O | [推断] 隔离器控制或GPIO |
| PC15 | PC15 (Pin3) | NC (或外接32.768kHz晶振) | - | [推断] 未使用或RTC晶振 |
| PA0 | PA0 (Pin7) | 接ISOGND | - | [推断] 用于ADC参考地或未使用 |

### 电源
- **供电输入**: +12V (CN1/CN2 2P端子)
- **隔离电源**: VPS8701B (U1-1) + 变压器 T1-1 (VPT87DFB01B) → 产生隔离5V 和 3.3V
- **非隔离5V**: 来自隔离电源二次侧
- **非隔离3.3V**: XC6206P332MR-G (U2-1) LDO，5V→3.3V，供电给 MCU 和数字部分
- **3.3VA**: 模拟供电，给运放 (U9/U10/U11) 和 ADC 参考
- **隔离地**: ISOGND（所有隔离侧电路共地）
- **非隔离地**: GND（电源输入侧）
- 电压基准 1.65V：由 R3(660Ω)+R4(820Ω) 分压网络产生（来自 3.3VA）

### 主要外部器件
- **U5 (CA-IS3721LS)**：SOIC-8 双通道数字隔离器，隔离 UART2 信号
- **OP1 (LM258DT)**：SOIC-8 双运放，用于信号调理
- **U8/U9/U10/U11 (SOP-8)**：四运放（具体型号未标注），用于恒流源、信号放大、滤波
- **Q1-Q4 (SS8050)**：NPN 晶体管，用于开关/驱动
- **D1**：SMB 封装的 TVS/整流管
- **D2-1/D3-1 (RB160M-30)**：肖特基二极管
- **R16 (0.1Ω)**：采样电阻 (R0805)
- **T1-1 (VPT87DFB01B)**：隔离变压器

## Build, Flash, And Run Notes

### 构建系统
- **IDE**: Keil MDK v5 (μVision)
- **编译器**: ARMCLANG V6.19
- **项目文件**: `battery_re/MDK-ARM/battery_re.uvprojx`
- **设备**: STM32G030F6Px

### 构建命令
```
C:\Keil_v5\UV4\UV4.exe -j0 -b "MDK-ARM/battery_re.uvprojx" -o "MDK-ARM/build_log.txt"
```
- `-j0`: 抑制弹窗
- `-b`: 增量编译
- `-o`: 日志输出到文件
- 退出码: 0=成功, 1=有Warning无Error, 2+=Error

### 烧录命令
```
pyocd flash -t stm32f103c8 build/firmware.elf
```
⚠️ 硬件配置中给出的是 `stm32f103c8` 目标，但实际 MCU 是 **STM32G030F6P6**。烧录时应使用 `-t stm32g030f6` 或相应的 target。此命令需修正。

### 串口监视
- **端口**: COM3 (硬件配置)
- **波特率**: 115200
- **数据格式**: 8N1 (标准UART)

### 主机测试命令
```
python host_tests/smoke_test.py --port COM7 --baud 115200
```

### 工作目录
```
C:\Users\123\Desktop\neizu\tasknew
```

### 输出产物
- `battery_re/MDK-ARM/battery_re/battery_re.axf` — ELF 可执行文件
- `battery_re/MDK-ARM/battery_re/battery_re.hex` — HEX 烧录文件
- `battery_re/MDK-ARM/battery_re/battery_re.map` — 链接映射表

### 时钟配置
- HSE: 8MHz 外部晶振
- PLL: PLLM=/1, PLLN=×16, PLLR=/2
- SysClk: 8MHz / 1 × 16 / 2 = **64MHz**
- Flash: 2 等待周期 (LATENCY_2)

### 内存布局
- **Flash (IROM)**: 0x08000000, 64KB (0x10000)
- **SRAM (IRAM)**: 0x20000000, 8KB (0x2000)

## 约束与风险

### 缺失信息
- **main.c** 和 **main.h** 文件已被删除，需要重新创建。之前的 main.c 中包含 `BOARD_PIN_PWM_AF` 宏 (`GPIO_AF2_TIM3`)，该宏在 STM32G0xx HAL 中可能已被弃用或命名不同（STM32G0 系列使用 `GPIO_AF2_TIM3` 应存在于 `stm32g0xx_hal_gpio.h` 中，上次编译错误表明头文件包含顺序有问题）。
- **stm32g0xx_hal_msp.c** 已被删除，需要重建。该文件包含外设的 HAL MSP 初始化代码（GPIO、DMA、NVIC 配置）。
- U8/U9/U10/U11 运放的具体型号未在 BOM 中标注（SOP-8 封装，无型号），但在原理图中有相关网络（如 `$3N880`-`$3N893` 为 U8 的多级滤波器网络）。实现中无需关心具体运放型号，只需关注 ADC 输入引脚的信号测量。
- PC14 (Pin2) 和 PC15 (Pin3) 的具体功能未完全明确，可能用于 RTC 晶振或作为 GPIO。

### 不清晰的硬件细节
- 隔离器 CA-IS3721LS 的使能/方向控制引脚连接细节不够清晰（U5.1=CN3.1=MCU PC14, U5.4=CN3.4=MCU...? 需确认）。
- U1-1 (VPS8701B) 隔离电源模块的配置细节不足。
- 网络 `$2N1217`（CN3.1-U3.2-U5.1）中 U3.2 和 U5.1 的具体连接功能需要从原理图进一步确认。

### 不确定的构建/烧录命令
- 硬件配置中给出的烧录命令使用 `stm32f103c8` 目标，与 STM32G030F6P6 不符。可能需要改为 `pyocd flash -t stm32g030f6 build/firmware.elf` 或使用 ST-Link Utility。
- CMake 构建命令 `cmake --build build` 不适用于 Keil 项目。应使用 UV4.exe 命令行。

### 不完整的验收标准
- 内阻测量精度目标未量化（如 ±1% 或 ±5mΩ）。
- 异常数据识别算法的具体判定标准未定义。
- 级联通讯协议的详细帧格式未在需求中给出（需要自定义设计）。

### 已截断或不可读的文件
- DS12991 数据手册转 Markdown 后表格格式部分错乱，但关键引脚表和功能描述可读。
- 部分 chunks 内容为空白或只有分页符，不影响整体理解。

### 真机验证风险
- 电池充放电场景下的强干扰可能影响 ADC 测量精度，异常数据识别算法需要在真实硬件上反复调试。
- 恒流注入电路（PWM→RC→运放）的 RC 参数和运放配置需要根据实际硬件特性调整。
- 级联通讯在多节点场景下可能存在总线冲突或时序问题。

## Confidence Assessment

| Section | Confidence | Reason |
|---------|-----------|--------|
| Goal | 高 | 用户需求清晰完整，功能目标明确 |
| Task Requirements | 高 | 需求文档详细列出了所有功能要求和实现步骤 |
| Hardware Connection | 中 | MCU 引脚与外设的映射已从网表和引脚表交叉验证，但部分网络信号的具体功能（如隔离器控制引脚）需要进一步原理图确认 |
| Build & Flash | 中 | Keil 项目结构完整可编译，但烧录命令中 target 型号错误（stm32f103c8 应为 stm32g030f6），需要修正 |
| Constraints & Risks | 中 | main.c/main.h/hal_msp.c 缺失需重建，通讯协议需自定义，异常检测算法需在真实硬件上验证 |
```