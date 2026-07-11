Now I have all the necessary information. Let me write the context.md.

```markdown
# Build Context

## Goal

完成电池内阻测量设备的固件开发。基于 STM32G030F6P6 (TSSOP-20)，使用 1kHz 交流注入法测量电池内阻，支持多电池手拉手 UART 级联通讯、DS18B20 温度测量、主机/从机自动识别。全部代码用状态机实现，无阻塞。项目根目录：`C:\Users\123\Desktop\neizu\tasknew\battery_re`。

## Source Materials

### Directory Overview

| Directory | Summary |
|-----------|---------|
| `battery_re/Core/Inc` | HAL 配置头文件 (`stm32g0xx_hal_conf.h`)、中断头文件 (`stm32g0xx_it.h`)。无用户级头文件。 |
| `battery_re/Core/Src` | 已有 `stm32g0xx_it.c`(中断服务)、`system_stm32g0xx.c`(系统时钟 64MHz 初始化)。**`main.c` 不存在**，需新建。 |
| `battery_re/Drivers/STM32G0xx_HAL_Driver` | STM32G0 HAL 驱动库完整源文件（ADC、TIM、UART、DMA、GPIO、RCC、FLASH、PWR、CORTEX、EXTI、IWDG 等）。 |
| `battery_re/Drivers/CMSIS` | CMSIS-Core 和 CMSIS-DSP (ARM Cortex-M0 数学库 `arm_cortexM0l_math.lib`)。 |
| `battery_re/MDK-ARM` | Keil MDK-ARM 项目文件 (`battery_re.uvprojx`)、启动文件 (`startup_stm32g030xx.s`)、链接脚本 (`battery_re.sct`)、编译输出。 |
| `.document-reader/BOM` | BOM 表格 (Excel→Markdown)，列出所有元器件。 |
| `.document-reader/BOM_Board1_Schematic1_2026-05-23` | 同上 BOM 的额外副本。 |
| `.document-reader/DS12991` | STM32G030x6/x8 数据手册 (DS12991 Rev 6)。 |
| `.document-reader/netlist` | 网表文件 (TEL→Markdown)，含完整元件互联和网络定义。 |

### Key Files Inspected

- `user_req.txt` — 用户需求文档，详细描述了功能、引脚分配、协议要求和实现步骤。
- `.document-reader/netlist/document.md` — 网表，包含所有网络连接定义。用于提取 MCU 引脚映射。
- `.document-reader/BOM/document.md` — BOM 表，含元器件型号、封装、Designator。
- `battery_re/Core/Src/system_stm32g0xx.c` — 系统初始化，时钟配置 HSE 8MHz→PLL→64MHz SysClk。
- `battery_re/Core/Src/stm32g0xx_it.c` — 中断服务程序，定义弱符号 `SCHED_IncTick` 和 `UART_IRQHandler` 供后续模块覆盖。
- `battery_re/Core/Inc/stm32g0xx_hal_conf.h` — HAL 模块选择，启用 ADC、TIM、UART、DMA、IWDG、EXTI。
- `battery_re/MDK-ARM/battery_re.uvprojx` — Keil 项目配置，MCU=STM32G030F6Px，ARMCLANG V6.19，输出 HEX。
- `battery_re/MDK-ARM/battery_re.sct` — 链接脚本：Flash 0x08000000(64KB)、RAM 0x20000000(8KB)。
- `battery_re/MDK-ARM/battery_re.lnp` — 链接器输入文件列表，显示已编译的 .o 文件列表。
- `battery_re/MDK-ARM/battery_re/battery_re.map` — 链接 map 文件，显示全局符号引用。
- `battery_re/MDK-ARM/battery_re/build_output.txt` — 最近成功编译日志：Code=5192 RO-data=288 RW-data=12 ZI-data=1580。
- `battery_re/MDK-ARM/battery_re/battery_re.htm` — 静态调用图，显示最大堆栈使用 224 字节。
- `__ds12991_tmp.txt` / `__out1.txt` — 数据手册摘录副本。
- `Netlist_Schematic1_2026-05-25.tel` — 原始网表文件。

## Task Requirements

**来源**: `user_req.txt`

**功能行为**:
- 使用 PWM 产生 1kHz 占空比 50% 方波，经 RC 滤波→正弦波→跟随器→运放恒流源，向电池注入交流电流。
- 测量电池两端产生的电压，结合注入电流计算电池内阻。**采样电阻 R16 = 0.1Ω** (从 BOM 确认)。
- 每隔固定分钟测量一次内阻（时间间隔未指定，需自行定义或做成可配置）。
- ADC 采集与电流注入**相位同步**，以 10kHz 采样率采集注入电流和电池端电压。
- 需校准电路导致的电流-电压相位差。
- 支持使用实际电阻对注入电流和采集电压进行多点校准。
- 异常数据识别算法：充电/放电时逆变器和充电器可能产生干扰，需丢弃异常数据。

**接口与协议**:
- **UART1** (主机端)：连接下一个电池的从机，作为主机发送指令。需要支持地址分配、读取所有从机的电压/电流/内阻/温度等数据。
- **UART2** (从机端)：接收上一个主机的指令。
- **UART 级联协议需自定义**：主机为所有从机分配地址，主机轮询读取 1#→2#→3#→... 的数据。
- **DQ (GPIO)**：DS18B20 温度传感器，30 秒测量一次温度。

**主机/从机识别**:
- **Pin 12 (M_S)**：内部上拉后读取电平。低电平=主机，高电平=从机。开机判断一次，之后改为输入模式省电。

**输出与指示**:
- 未指定具体指示方式（LED/无），需自行设计。

**时序与性能**:
- 所有代码不得阻塞，全部使用状态机。
- 10kHz ADC 采样，与 1kHz 注入电流相位同步。
- 1kHz PWM 输出 (TIM3_CH3)。
- 系统时钟 64MHz。

**测试与验收标准**:
- 能够通过 Keil 编译（ARMCLANG V6.19）。
- 能够烧录运行完成内阻测量、温度测量、UART 级联通讯功能。

## Hardware Connection

### MCU / SoC

- **Part number**: STM32G030F6P6TR
- **Core**: Arm Cortex-M0+, 64MHz max
- **Package**: TSSOP-20 (6.5×4.4mm, 0.65mm pitch)
- **Flash**: 32KB (0x08000000–0x08007FFF)
- **SRAM**: 8KB (0x20000000–0x20001FFF)
- **BOM Designator**: U3-1

### Debug / Flash Interface

- **Protocol**: Serial Wire Debug (SWD)
- **Connector**: H5 (B-2100S04P-A110, 4-pin header 2.54mm)
  - H5.1 = 3.3V
  - H5.2 = ISOGND
  - H5.3 = SWDIO (MCU pin 18)
  - H5.4 = SWCLK (MCU pin 19)
- **Required tools**: J-Link / ST-Link / DAP-Link + Keil MDK

### Power

- **MCU VDD**: 3.3V (pin 4)
- **Regulator**: XC6206P332MR-G (U2-1, SOT-23-3), 3.3V LDO
  - Input: 5V → Output: 3.3V
- **VDD domains**:
  - `3.3V` — MCU VDD, U5 isolator VDD_B, pull-ups, U2-1 input/output
  - `3.3VA` — 模拟供电 (Q1/Q3, op-amp, U8/U9/U10/U11 VDD)
  - `5V` — LDO input, schottky diodes
  - `5VA` — OP1 (LM258) supply
  - `+12V` — 功率部分 (VPS8701B 电源芯片输入)
  - `1.65V` — 参考电压 (TLV431 分压产生)
- **GND domains**:
  - `GND` — 初级地 (CN1/CN2, U1-1)
  - `ISOGND` — 隔离地 (所有其他器件地，通过 U5 隔离)
- **ESD protection**: SMAJ15CA (D1-1) TVS, RB160M-30 (D2-1, D3-1) schottky
- **Fuse**: 0603L050YR (F1-1) PTC 自恢复保险

### Peripheral Wiring

网表中的 MCU 引脚编号格式为 `U3-1.<pin>`。

| 信号名 | MCU Pin# | 目标器件/模块 | 方向 | 说明 |
|--------|----------|---------------|------|------|
| **UART1_RX** | 1 | CN4.3 (外接下一个电池 UART 从机的 TX) | IN | 通过 R11(10Ω) 串联 |
| **UART1_TX** | 20 | CN4.2 (外接下一个电池 UART 从机的 RX) | OUT | 通过 R10(10Ω) 串联 |
| **NRST** | 6 | NRST 线路, U6 (电容) | IN | 外部复位 |
| **VDD** | 4 | 3.3V 供电 | PWR | |
| **VSS** | 5, 7 | ISOGND | PWR | 两个 VSS 引脚 |
| **VOLT_ADC** | 8 | 运放 OP1 输出 (电池电压信号) | IN | ADC 输入通道，测量电池端电压 |
| **UART2_TX** | 9 | U5.6→U5.1→CN3.1 (向上一个电池主机的 RX) | OUT | 经过 CA-IS3721LS 隔离，通过 R8(10Ω) |
| **UART2_RX** | 10 | U5.7→U5.4→CN3.4 (向上一个电池主机的 TX) | IN | 经过 CA-IS3721LS 隔离，通过 R7(10Ω) |
| **DQ** | 11 | H6.2 (DS18B20 数据线) | I/O | 4.7kΩ (R6) 上拉到 3.3V |
| **M_S** | 12 | R9(100k) 上拉到 ISOGND | IN | 主从选择，内部上拉后读电平；低=主机 |
| **CURRENT_ADC** | 13 | 电流检测运放 U11.1 输出 | IN | ADC 输入通道，测量注入电流 (通过 R16 采样) |
| **RES_ADC** | 14 | 电压检测运放 U10.7 输出 | IN | ADC 输入通道，测量电阻电压 |
| **TIM3_CH3** | 15 | R21(100k) → 滤波电路 | OUT | 1kHz 50% 占空比 PWM，产生交流注入信号 |
| **SWDIO** | 18 | H5.3 (SWD 调试接口) | I/O | |
| **SWCLK** | 19 | H5.4 (SWD 调试接口) | IN | |
| **UART1_TX** | 20 | CN4.2 | OUT | 见上行 |

**连接器引脚定义**:
- **CN1, CN2** (HT396V-3.96-2P): 电池连接端子 (2-pin, 3.96mm)
  - CN1.1 / CN2.1 = +12V
  - CN1.2 / CN2.2 = GND (初级)
- **CN3** (KF2EDGV-2.54-4P, xh2.54-4p): 与前一个电池的 UART 隔离接口
  - CN3.1 → U5.1 (→隔离→ U5.6 → R8 → UART2_TX)
  - CN3.2 → U5.2 (未连接 MCU [推断：隔离器配置/NC])
  - CN3.3 → U5.3 (未连接 MCU [推断：隔离器配置/NC])
  - CN3.4 → U5.4 (→隔离→ U5.7 → R7 → UART2_RX)
- **CN4** (KF2EDGV-2.54-4P, xh2.54-4p): 与下一个电池的 UART 直连接口
  - CN4.1 = 3.3V
  - CN4.2 → R10 → UART1_TX
  - CN4.3 → R11 → UART1_RX
  - CN4.4 = ISOGND
- **H1-H4** (battery_pin, 1×1 排针): 电池检测连接
  - H1.1 = RES_SENSOR-
  - H2.1 = ISOGND
  - H3.1 = 通过 100nF(C16)到... [推断：可能为屏蔽/测试点]
  - H4.1 = 通过 100nF(C25)到... [推断：可能为屏蔽/测试点]
- **H5** (B-2100S04P-A110, 4-pin): SWD 调试口
- **H6** (xh2.54-3p): DS18B20 接口
  - H6.1 = 3.3V
  - H6.2 = DQ
  - H6.3 = ISOGND

**隔离器 U5 (CA-IS3721LS)**:
- 2 通道数字隔离器，SOIC-8
- 隔离 UART2 信号 (MCU 侧 = 3.3V/ISOGND, 总线侧 = CN3)
- [推断] U5.2/U5.3 可能未用或用于 CTS/RTS 流控

**运放电路**:
- **OP1 (LM258DT)**: 电压调理运放，输出 VOLT_ADC → MCU pin 8
- **U8-U11 (SOP-8)**: [推断] 多路运放/模拟开关，用于信号调理
  - U8: 与电流信号相关 (3N880-3N893 网络)
  - U9: 与 PWM 驱动/恒流控制相关 (4N1456-4N2695 网络)
  - U10: 电压检测调理 (RES_ADC 输出)
  - U11: 电流检测调理 (CURRENT_ADC 输出)
- **采样电阻 R16**: 0.1Ω (R0805), 用于注入电流检测

**电源部分**:
- **U1 (TLV431AIDBZR)**: 可调 shunt 稳压器，产生 1.65V 参考电压 (R3=680Ω, R4=820Ω, R5=2.49kΩ 分压)
- **U1-1 (VPS8701B)**: DC-DC 电源芯片 (SOT-23-6)，隔离电源产生
- **T1-1 (VPT87DFB01B)**: 变压器，用于隔离电源

### Uncertainties

- **TIM3_CH3 (pin 15)** 的 GPIO 端口名未从文档中明确确认。[推断] 根据 STM32G030F6P6 TSSOP20 数据手册，pin 15 = PA5 (TIM2_CH1) 或 PA0 (TIM3_CH1)... 与实际电路设计不符。实际可靠依据是网表标注为 TIM3_CH3，请参考 STM32G030F6P6 datasheet Table 12 确认该引脚具体 GPIO 端口。
- U5 (CA-IS3721LS) 引脚 2、3 连接 CN3.2/CN3.3 但未连接到 MCU 任何引脚。[推断] 可能用于硬件流控 (RTS/CTS) 或悬空配置。
- U8/U9/U10/U11 (SOP-8) 具体型号未在 BOM 中列出（空白），[推断] 可能为通用运放 (如 LMV324 系列) 或模拟开关。需参考实际硬件。
- 内阻测量周期（每隔几分钟）由用户需求指定为"定时"但未给出具体值。需要软件中定义为可配置参数。
- 异常数据识别算法需自行设计，无具体算法要求。

## Build, Flash, And Run Notes

### Build System & Toolchain
- **IDE**: Keil MDK-ARM (μVision)
- **Toolchain**: ARMCLANG V6.19 (Arm Compiler for Embedded 6.19)
- **Compiler path**: `C:\Keil_v5\UV4\UV4.exe`
- **Device Pack**: Keil.STM32G0xx_DFP.1.4.0
- **DSP Library**: `Drivers\CMSIS\DSP\Lib\ARM\arm_cortexM0l_math.lib` (已链接)

### Build Command
```
"C:\Keil_v5\UV4\UV4.exe" -j0 -b "MDK-ARM/battery_re.uvprojx" -o "MDK-ARM/build_log.txt"
```
- `-j0`: 抑制弹窗
- `-b`: batch build (增量编译)
- `-r`: 如需全量 rebuild

### Build Output
- 工作目录: `battery_re/MDK-ARM/`
- 输出文件: `battery_re/battery_re.axf`, `battery_re/battery_re.hex`, `battery_re/battery_re.map`
- 最近编译: Code=5192, RO-data=288, RW-data=12, ZI-data=1580
- 最大堆栈: 224 字节 (不含不可追踪函数指针)

### Flash Command
使用 Keil MDK 的 Flash 下载功能（通过 UL2CM3.DLL 驱动，使用 STM32G0xx_32.FLM 算法）。
可通过 μVision IDE 直接点击 Download 烧录。
[推断] 也可使用外部工具如 ST-Link Utility 烧录 .hex 文件。

### Serial / Debug
- UART 调试输出：未指定具体 UART（可复用 UART1 或 UART2，或使用 SWO）。
- 如需串口输出：建议使用 UART1 或 USART，波特率待定（建议 115200 或 9600）。

### Required Files To Create
需要新建的文件（不在当前项目中）：
- `Core/Src/main.c` — 主程序入口
- `Core/Inc/main.h` — 主头文件（已有外部变量声明被 `stm32g0xx_it.c` 引用）
- `Core/Src/stm32g0xx_hal_msp.c` — HAL MSP 初始化（从 map 看已存在 .o，但源文件不在 Core/Src 中，可能之前被删除）

[推断] `stm32g0xx_hal_msp.c` 之前存在于项目中并已编译，但源文件已丢失。需重新创建。
[推断] 从 map 文件看，`main.o` 也已被编译过（但 main.c 源文件已删除），需要重新创建 main.c。

### Project Groups (from .uvprojx)
Keil 项目中已定义以下 Groups，新建的源文件需添加到对应的 Group：
1. **Application** (当前为空) — 建议存放用户应用代码
2. **Drivers/STM32G0xx_HAL_Driver** — 21 个 HAL 源文件
3. **Drivers/CMSIS** — `system_stm32g0xx.c` + `arm_cortexM0l_math.lib`

### Build Exit Codes
- 0: 成功 (0 error 0 warning)
- 1: 仅有 warning (仍算通过)
- 2–20: 编译 error
- 21+: fatal error

## Constraints And Risks

- **main.c 和 main.h 不存在**：需从头创建，需确保与现有 `stm32g0xx_it.c` 中的 `extern` 声明匹配（hadc1, htim3, htim14, hdma_adc1, huart1, huart2）。
- **stm32g0xx_hal_msp.c 不存在**：需重新创建，包含 ADC、TIM、UART 的 MSP 初始化/去初始化函数。
- **U8/U9/U10/U11 型号未知**：无法精确知道模拟通路参数。需留出调理电路配置接口。
- **CA-IS3721LS 引脚功能**：未获取详细数据手册。默认按 2 通道数字隔离器处理。
- **DS12991 数据手册 Markdown 转换**：引脚定义表渲染混乱，无法直接获取 GPIO 端口名与封装引脚的对应关系。建议参考原始 PDF 数据手册。
- **用户需求中 ADC 触发方式**：要求 10kHz 采样且与 1kHz 注入电流相位同步。建议使用 TIM3 的 TRGO 触发 ADC 注入组转换，或使用定时器更新事件触发 ADC 实现固定频率采样。
- **内阻测量周期未指定**：需在软件中定义默认值（如 1 分钟），并做成可配置宏。
- **异常数据识别算法无具体要求**：需要自行设计算法（如滑动窗口、超出标准差阈值丢弃等）。
- **校准方法**：需要设计多点校准接口（实际电阻值与 ADC 读数的映射）。

## Confidence Assessment

| Section | Confidence | Reason |
|---------|-----------|--------|
| Goal | High | 用户需求描述清晰详细。 |
| Task Requirements | High | `user_req.txt` 有完整功能列表、协议要求、实现步骤。仅有少量未指定细节（测量周期、异常算法）。 |
| Hardware Connection | Medium | 从网表提取了 MCU 引脚映射（可靠）。但 GPIO 端口名（PAx/PBx）无法从文档确认，U8-U11 型号未知，CA-IS3721LS 详细 pinout 未验证。 |
| Build & Flash | High | Keil 项目配置完整，已知编译命令和输出。包含所有必要的 HAL 驱动。 |
| Constraints & Risks | Medium | main.c/hal_msp.c 缺失但结构清晰可重建。主要风险是模拟电路细节不完整和引脚端口名的确认。 |
```