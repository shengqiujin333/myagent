Now I have sufficient information. Let me compile the context.md.

```
# Build Context

## Goal
完成电池内阻测量系统的嵌入式固件开发。核心功能：使用 STM32G030F6P6 (TSSOP-20) 产生 1kHz 占空比 50% 的 PWM 方波，经过 RC 滤波形成正弦波，通过恒流源电路向电池注入交流电流；同步采集电池两端电压，计算电池内阻；每 1 分钟测量一次；支持 DS18B20 测温（每 30s）；支持电池组手拉手 UART 级联通讯；主/从机自动识别；整体采用状态机框架，禁止阻塞。

**目标硬件**: STM32G030F6P6 (TSSOP-20)，Keil MDK-ARM (ArmClang V6.19) 编译，SWD 调试/烧录。

**预期产出**: 在 `battery_re/` 工程中添加完整应用代码，通过 Keil 编译 0 Error 0 Warning。

## Source Materials

### Directory Overview

| Directory | Summary |
|-----------|---------|
| `battery_re/Drivers/CMSIS/` | CMSIS 核心层，含 Device/ST/STM32G0xx 外设访问层、DSP 库 (arm_cortexM0l_math.lib) |
| `battery_re/Drivers/STM32G0xx_HAL_Driver/` | STM32G0xx HAL 驱动源码 (Inc/Src)，已启用：ADC、TIM、UART、GPIO、DMA、RCC、FLASH、PWR、EXTI、IWDG |
| `battery_re/MDK-ARM/` | Keil uVision 项目文件 (.uvprojx)、启动文件、链接脚本、编译输出 |
| `battery_re/Core/Inc/` | 用户头文件：`stm32g0xx_hal_conf.h`、`stm32g0xx_it.h` |
| `battery_re/Core/Src/` | 用户源文件：`stm32g0xx_it.c`、`system_stm32g0xx.c`（**main.c 和 stm32g0xx_hal_msp.c 在工程中注册但当前目录中不存在** — 需由后续阶段创建） |
| `.document-reader/` | 硬件文档的 Markdown 版本：网表 (netlist)、BOM、DS12991 数据手册 |
| `.understand-anything/` | 上一次分析生成的中间文件（可忽略） |

### Key Files Inspected

- `user_req.txt` — 用户需求文档，包含完整功能描述、引脚分配、通讯协议要求、编译命令
- `Netlist_Schematic1_2026-05-25.tel` — 原始网表文件
- `.document-reader/netlist/document.md` — 网表 Markdown 版，包含所有网络连接、器件封装
- `.document-reader/BOM/document.md` — BOM 表，列出所有元器件型号、封装、制造商
- `.document-reader/DS12991/document.md` — STM32G030x6/x8 数据手册（PDF 转 Markdown，部分表格渲染有损）
- `battery_re/MDK-ARM/battery_re.uvprojx` — Keil 项目配置，已注册源文件组、宏定义 (`USE_HAL_DRIVER,STM32G030xx`)、包含路径
- `battery_re/MDK-ARM/startup_stm32g030xx.s` — 启动文件（Stack 0x400, Heap 0x200）
- `battery_re/Core/Src/system_stm32g0xx.c` — 系统初始化，HSE 8MHz -> PLL -> 64MHz SysClk
- `battery_re/Core/Src/stm32g0xx_it.c` — 中断服务函数框架，含弱符号桩函数 `SCHED_IncTick()`、`UART_IRQHandler()`
- `battery_re/Core/Inc/stm32g0xx_it.h` — 中断声明，已列出所需外设中断：DMA1_CH1、ADC1、TIM1_BRK_UP_TRG_COM、TIM3、TIM14、USART1、USART2
- `battery_re/Core/Inc/stm32g0xx_hal_conf.h` — HAL 模块配置（启用 ADC、TIM、UART、GPIO、DMA、RCC、FLASH、PWR、EXTI、IWDG）
- `battery_re/MDK-ARM/build_log.txt` — 最近一次成功编译日志（0 Error, 0 Warning），验证了工具链和工程配置可用
- `battery_re/MDK-ARM/battery_re/battery_re.sct` — 链接脚本：Flash 0x08000000 (64KB), RAM 0x20000000 (8KB)

## Task Requirements

### 功能行为
- 使用 **TIM3_CH3** 产生 **1kHz 占空比 50% 方波**，经 RC 滤波 -> 正弦波，通过恒流源电路向电池注入交流电流
- 在电池两端采样电压，结合采样电阻（**0.1Ω**，R16）计算注入电流，进而计算电池内阻
- 每 **1 分钟** 测量一次电池内阻
- **DS18B20** 单总线测温（DQ 线），每 **30s** 测量一次
- 通过 **UART1** 作为主机与下一级从机通讯；通过 **UART2** 作为从机接收上一级主机指令
- 板级主/从判断：**Pin12 (M/S)** 上拉输入，低电平=主机，高电平=从机，开机判断一次后改输入模式省电
- 主机开机后给从机分配地址，定时轮询所有从机的电压、内阻、温度等数据
- 整体使用 **状态机** 架构，禁止阻塞

### 接口和协议
- **UART1** (主机端): TX=Pin20 (PB6), RX=Pin1 (PB7)，与下一级电池板通讯
- **UART2** (从机端): TX=Pin9 (PA2), RX=Pin10 (PA3)，接收上一级主机指令
- 自定义级联通讯协议（需设计并输出协议文档）
- 支持地址分配、数据轮询（电压、注入电流、内阻、温度等可扩展数据）

### 输出和指示
- 交流恒流注入：1kHz 正弦波，通过 RC 滤波器 + 跟随器 + 运放产生
- 采样电阻 **R16 = 0.1Ω (0805)**，用于电流检测
- ADC 以 **10kHz** 采样电压，需与注入电流相位同步
- 需对电路引入的注入电流与电压之间的相位差进行软件校正
- 需支持使用实际电阻对电流/电压采集进行多点校准

### 时序和性能
- PWM: 1kHz, 50% 占空比 (TIM3_CH3)
- ADC: 10kHz 采样，相位同步
- 测量周期: 每 1 分钟
- 温度测量: 每 30s
- 系统时钟: 64MHz (HSE 8MHz → PLL → 64MHz)
- 整体非阻塞状态机

### 测试和验收标准
- Keil MDK-ARM 编译通过，0 Error 0 Warning
- 编译命令: `UV4.exe -j0 -b "MDK-ARM/battery_re.uvprojx" -o "MDK-ARM/build_log.txt"`
- 退出码 0（成功）或 1（有 warning 但无 error）
- 需输出软件架构设计、模块划分、各模块设计方案、通讯协议设计文档

## Hardware Connection

### MCU / SoC
- **Part number**: STM32G030F6P6TR
- **Core / architecture**: ARM Cortex-M0+, 64MHz max
- **Package**: TSSOP-20 (6.5×4.4mm, 0.65mm pitch)
- **Flash**: 64KB (0x08000000–0x0800FFFF)
- **SRAM**: 8KB (0x20000000–0x20001FFF)
- **Datasheet**: ST DS12991 Rev 6

### Debug / Flash Interface
- **Protocol**: SWD (Serial Wire Debug)
- **Connector**: H5 (B-2100S04P-A110, 4-pin header 2.54mm)
  - Pin 1: 3.3V
  - Pin 2: GND (ISOGND)
  - Pin 3: SWDIO (PA13, MCU Pin 18)
  - Pin 4: SWCLK (PA14, MCU Pin 19)
- **Flash tool**: pyocd flash -t stm32f103c8 build/firmware.elf（**注：硬件配置中 flash 命令使用了错误的 target stm32f103c8，应为 stm32g030f6 或类似）**
- **Debug tool**: Keil UL2CM3 或 J-Link / pyOCD

### Peripheral Wiring

| Signal | MCU Pin | MCU Port | Target Device / Module | Direction | Notes |
|--------|---------|----------|----------------------|-----------|-------|
| UART1_TX | 20 | PB6 (AF0) | 下一级电池板 UART1_RX | OUT | 主机发送，经 R10 (10Ω) 到 CN4.3 |
| UART1_RX | 1 | PB7 (AF0) | 下一级电池板 UART1_TX | IN | 主机接收，经 R11 (10Ω) 到 CN4.2 |
| UART2_TX | 9 | PA2 (AF1) | 上一级电池板 UART2_RX | OUT | 从机发送，经 R8 (10Ω) 到 CN3.2 |
| UART2_RX | 10 | PA3 (AF1) | 上一级电池板 UART2_TX | IN | 从机接收，经 R7 (10Ω) 到 CN3.1 |
| TIM3_CH3 | 15 | PB0 (AF2) | RC 滤波电路 → 恒流源 | OUT | 1kHz PWM 方波输出，经 R21 (100K) |
| DQ | 11 | PA4 (GPIO) | DS18B20 (H6.2) | I/O | 单总线，经 R6 (4.7kΩ) 上拉到 3.3V |
| M/S | 12 | PA5 (GPIO) | 上拉电阻 R9 (100K) 到 3.3V | IN | 主从判断：低=主机，高=从机 |
| VOLT_ADC | 8 | PA1 (ADC_IN1) | 电池电压分压采样 | IN | 经 R4-1/R5-1 (100kΩ) 分压到 1.65V 偏置 |
| CURRENT_ADC | 13 | PA6 (ADC_IN6) | 电流检测运放输出 U11.1 | IN | 经 R52 (100kΩ) |
| RES_ADC | 14 | PA7 (ADC_IN7) | 内阻检测运放输出 U10.7 | IN | 经 R38 (10kΩ) |
| SWCLK | 19 | PA14 | SWD 调试接口 H5.4 | IN | 调试时钟 |
| SWDIO | 18 | PA13 | SWD 调试接口 H5.3 | I/O | 调试数据 |
| NRST | 6 | NRST | 复位电路 U6.1 | IN | 外部复位 |
| VDD/VDDA | 4 | VDD | 3.3V 供电 | PWR | XC6206P332MR (3.3V LDO) 输出 |
| VSS/VSSA | 5, 7 | VSS | GND / ISOGND | PWR | 模拟地和数字地分开 |

### 关键电路模块

| 模块 | 主要器件 | 功能 |
|------|---------|------|
| 电源 | U2-1 (XC6206P332MR, SOT-23-3) | 5V→3.3V LDO |
| 隔离电源 | U1-1 (VPS8701B), T1-1 (VPT87DFB01B) | 隔离 5V 供电 |
| 隔离通讯 | U5 (CA-IS3721LS, SOIC-8) | UART 隔离，连接 CN3（隔离侧） |
| 信号调理 | OP1 (LM258DT, SOIC-8) | 运放，1.65V 偏置处理 |
| 电流检测 | U11 (SOP-8), R16 (0.1Ω/0805) | 采样电阻 + 差分放大器 |
| 内阻检测 | U10 (SOP-8), U9 (SOP-8) | 同步检波/滤波 |
| 电压基准 | U1 (TLV431AIDBZR, SOT-23-3) | 1.25V 可调基准，经分压产生 1.65V 偏置 |
| 保护 | F1-1 (0603L050YR), D1-1 (SMAJ15CA) | 自恢复保险 + TVS |
| 电池连接 | H1, H2, H3, H4 (battery_pin) | 电池四线法连接（RES_SENSOR+ / RES_SENSOR-） |
| 级联连接器 | CN3, CN4 (KF2EDGV-2.54-4P) | 4pin 级联接口 |
| 电源连接器 | CN1, CN2 (HT396V-3.96-2P) | 2pin 电源输入 (+12V / GND) |
| DS18B20 接口 | H6 (xh2_54-3p) | 3pin 连接器：3.3V, DQ, GND |

### Power
- **Supply input**: +12V (CN1, CN2)
- **Primary LDO**: XC6206P332MR (3.3V, SOT-23-3) — 5V→3.3V
- **Isolated supply**: VPS8701B + VPT87DFB01B 变压器隔离
- **Analog supply**: 3.3VA (separate from digital 3.3V)
- **Reference voltage**: 1.65V (由 TLV431 + 分压电阻 R3=660Ω, R4=820Ω 等产生)
- **偏置**: 所有 ADC 信号以 1.65V 为中心偏置

### 不确定信息
- [推断] DS18B20 的具体型号未在 BOM 中列出，但 DQ 网络连接 H6.2，通过 4.7kΩ 上拉到 3.3V，符合 DS18B20 典型应用
- [推断] U8/U9/U10/U11（SOP-8）的具体型号未在 BOM 中列出，从电路连接判断 U9/U10 可能为同步检波/滤波器（如 AD630 或类似运放），U11 可能为差分电流检测放大器
- [推断] 1.65V 偏置产生：从 TLV431 (1.25V) 通过 R3/R4 分压或 R47/R48 分压产生
- 隔离 UART 侧 (CN3) 的具体接法需确认 CA-IS3721LS 的数据手册
- 实际硬件中 ADC 通道与 MCU 引脚的映射需确认（PA1=ADC_IN1, PA6=ADC_IN6, PA7=ADC_IN7）

## Build, Flash, And Run Notes

### 构建系统
- **IDE/Toolchain**: Keil MDK-ARM V5, ArmClang V6.19, 器件包 Keil.STM32G0xx_DFP.1.4.0
- **项目文件**: `MDK-ARM/battery_re.uvprojx`
- **编译命令**: `C:\Keil_v5\UV4\UV4.exe -j0 -b "MDK-ARM/battery_re.uvprojx" -o "MDK-ARM/build_log.txt"`
- **工作目录**: `C:\Users\123\Desktop\neizu\tasknew\battery_re`
- **编译宏**: `USE_HAL_DRIVER,STM32G030xx`

### 包含路径
- `../Core/Inc`
- `../Drivers/STM32G0xx_HAL_Driver/Inc`
- `../Drivers/STM32G0xx_HAL_Driver/Inc/Legacy`
- `../Drivers/CMSIS/Device/ST/STM32G0xx/Include`
- `../Drivers/CMSIS/Include`
- `..\Drivers\CMSIS\DSP\Include`

### 输出产物
- `MDK-ARM/battery_re/battery_re.axf` — ELF 可执行文件
- `MDK-ARM/battery_re/battery_re.hex` — Intel HEX 烧录文件
- `MDK-ARM/battery_re/battery_re.map` — 链接映射表

### 烧录
- **Debug接口**: SWD (PA13=SWDIO, PA14=SWCLK, 3.3V, GND) via H5 4-pin header
- **Flash命令（硬件配置中提供）**: `pyocd flash -t stm32f103c8 build/firmware.elf`（⚠️ `stm32f103c8` 是错误的 target，应为 `stm32g030f6`）
- **Keil 内置烧录**: UL2CM3 驱动，使用 STM32G0xx_32.FLM 算法

### 串口调试
- **端口**: COM3（硬件配置），**实际级联中 UART1/2 均为级联口，无独立调试串口**
- **波特率**: 115200（硬件配置）
- **注意**: 板上无独立调试 UART（无 USB-TTL 转换）；级联 UART 即为功能通讯口

### 时钟配置
- HSE 8MHz 外部晶振 → PLL (M=1, N=16, R=2) → SysClk = 64MHz
- APB 定时器时钟 = 64MHz

### 内存布局
- Flash: 0x08000000, 64KB
- RAM: 0x20000000, 8KB
- Stack: 0x400 (1KB)
- Heap: 0x200 (512B)

## Constraints And Risks

### 缺失信息
1. **main.c 不存在** — 需在 `Core/Src/main.c` 创建，包含 HAL Init、外设初始化、主状态机
2. **stm32g0xx_hal_msp.c 不存在** — 需创建，实现外设的 HAL MSP 初始化（GPIO、DMA、UART、TIM、ADC 等）
3. **U8/U9/U10/U11 具体型号未知** — SOP-8 封装，功能无法精确定位，需根据电路行为推断或查阅 PCB 设计
4. **DS18B20 具体接法** — 假设标准寄生供电或外部供电（H6 提供 3 线：VCC, DQ, GND）
5. **级联 UART 波特率未指定** — 需自行定义（建议 115200 或 9600）
6. **通讯协议未定义** — 需自行设计自定义协议（地址分配、数据帧格式、校验等）
7. **校准参数** — 相位校正系数、多点校准表需定义但初始值未知

### 不明确的硬件细节
- 隔离侧 (CA-IS3721LS) 与 MCU 侧的 UART 电平匹配需确认
- ADC 采样率 10kHz 与 PWM 1kHz 的相位同步实现方式（使用 TIM 触发 ADC 或 DMA 双缓冲）
- 模拟偏置 1.65V 的具体生成电路需确认（TLV431 或电阻分压）
- 实际相位差（电路引入）的数值未知，需通过实验标定

### 不确定的构建/烧录命令
- `pyocd flash -t stm32f103c8` 明显错误，需要 `stm32g030f6` 或 `stm32g030f6p6`
- 建议使用 Keil 自带烧录或修正 pyOCD 命令

### 不完整的验收标准
- 无具体内阻测量精度要求
- 无通讯协议测试向量
- 无异常数据识别算法的具体指标

### 截断或不可读文件
- DS12991 数据手册 PDF→Markdown 转换中表格渲染严重有损，无法直接读取精确的引脚映射表
- 网表文件渲染为 Markdown 后格式基本完整可用

### 实机验证风险
- 单板无法独立测试级联通讯功能
- 电池内阻测量需真实电池或 RC 模拟负载
- 异常数据识别算法需实际充电/放电干扰环境验证

## Confidence Assessment

| Section | Confidence | Reason |
|---------|-----------|--------|
| Goal | High | 用户需求文档清晰，功能描述完整 |
| Task Requirements | High | 所有要求来自 `user_req.txt` 原文，引述明确 |
| Hardware Connection | Medium | 网表提供了完整引脚映射，但部分 IC 型号（U8/U9/U10/U11）未知，DS12991 数据手册表格渲染有损，TSSOP-20 引脚映射为推断结合网表确认 |
| Build & Flash | High | 已成功编译验证 (0 Error)，项目文件配置完整 |
| Constraints & Risks | High | 缺失项已明确列出，来源清晰 |
```