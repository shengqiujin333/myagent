# Build Context

## Goal

基于 STM32G030F6P6 (TSSOP-20) 开发电池内阻测量系统，使用 Keil MDK-ARM 编译。系统通过 PWM 产生 1kHz 占空比 50% 方波，经 RC 滤波形成正弦波，再通过运放产生交流恒流注入电池。同步采集电池两端电压和注入电流，计算内阻。每 1 分钟测量一次。支持 DS18B20 温度测量（每 30s）、UART 级联多机通讯（主从自动识别）、异常数据识别与相位校准。全部使用状态机，禁止阻塞。

## Source Materials

### Directory Overview

| 目录 | 说明 |
|------|------|
| `battery_re/` | Keil MDK-ARM 项目根目录，包含 Core、Drivers、MDK-ARM 子目录 |
| `battery_re/Core/Inc/` | HAL 配置文件 (`stm32g0xx_hal_conf.h`)、中断头文件 (`stm32g0xx_it.h`) |
| `battery_re/Core/Src/` | 已有文件：`stm32g0xx_it.c`（带弱符号桩）、`system_stm32g0xx.c`（64MHz 时钟配置） |
| `battery_re/Drivers/CMSIS/` | CMSIS Core、Device、DSP 库、RTOS |
| `battery_re/Drivers/STM32G0xx_HAL_Driver/` | STM32G0 HAL 驱动（ADC、RCC、TIM、UART、GPIO、DMA、PWR、FLASH、EXTI、IWDG） |
| `battery_re/MDK-ARM/` | Keil 项目文件 (`battery_re.uvprojx`)、启动文件 (`startup_stm32g030xx.s`)、构建脚本 (`.BAT`) |
| `.document-reader/` | 硬件文档索引：DS12991 数据手册、网表、BOM 的 Markdown 摘要 |
| `.understand-anything/` | 知识图谱缓存 |

### Key Files Inspected

| 文件 | 说明 |
|------|------|
| `user_req.txt` | 用户需求文档 — 详细描述功能、引脚分配、通讯协议要求 |
| `Netlist_Schematic1_2026-05-25.tel` | 网表文件 — 所有元件的网络连接，包括 MCU 引脚分配 |
| `__ds12991_tmp.txt` | STM32G030x6/x8 数据手册摘要 |
| `.document-reader/BOM/document.md` | BOM 表 — 所有元件的型号、封装、值 |
| `.document-reader/BOM_Board1_Schematic1_2026-05-23/document.md` | 第二份 BOM（与第一份内容一致） |
| `.document-reader/netlist/document.md` | 网表 Markdown 版本 |
| `.document-reader/DS12991/document.md` | DS12991 数据手册全文 (298KB, 127 chunks) |
| `battery_re/MDK-ARM/battery_re.uvprojx` | Keil 项目配置 — 设备、包含路径、源文件列表 |
| `battery_re/MDK-ARM/battery_re.BAT` | 手动构建批处理文件 |
| `battery_re/Core/Inc/stm32g0xx_hal_conf.h` | HAL 模块启用配置（ADC、TIM、UART、DMA、GPIO、RCC、FLASH、PWR、EXTI、CORTEX、IWDG） |
| `battery_re/Core/Inc/stm32g0xx_it.h` | 中断函数声明 |
| `battery_re/Core/Src/stm32g0xx_it.c` | 中断服务程序（含弱符号桩 `SCHED_IncTick`、`UART_IRQHandler`）|
| `battery_re/Core/Src/system_stm32g0xx.c` | 系统时钟初始化（HSE 8MHz → PLL → 64MHz SysClk）|
| `battery_re/MDK-ARM/startup_stm32g030xx.s` | 启动文件（Stack=0x400, Heap=0x200，完整向量表）|
| `battery_re/MDK-ARM/build_log.txt` | 成功构建日志（0 Error, 0 Warning）|

## Task Requirements

### 功能行为
- MCU 产生 1kHz 占空比 50% 方波（TIM3_CH3），通过外部 RC 滤波 → 正弦波 → 跟随器 → 运放恒流源，向电池注入交流电流
- 采样电阻 0.1Ω（R16），用于测量注入电流
- 同步采集注入电流产生的电池两端电压（10kHz 采样率，与电流相位同步）
- 计算电池内阻 = 电压 / 电流
- 每 1 分钟测量一次内阻
- DS18B20 测温（DQ 引脚），30 秒测量一次
- 状态机驱动所有逻辑，禁止阻塞等待

### 接口和协议
- **UART1**：主机模式，与下一级电池从机通讯（发送指令、分配地址、读取数据）
- **UART2**：从机模式，接收上一级主机指令
- 自定义 UART 级联协议：主机分配地址（1/2/3…），主机轮询读取所有从机数据（电压、电流、内阻、温度等）
- M/S 引脚（pin12）：开机判断主从身份。上拉输入，若为低电平则为主机，否则为从机。判断后改为输入（省电）

### 输出和指示
- 交流恒流注入：TIM3_CH3 → 外部 RC + 运放电路
- ADC 采集：VOLT_ADC（电池电压）、CURRENT_ADC（注入电流）、RES_ADC（备用）
- UART 级联上报测量数据

### 时序和性能
- 注入频率：1kHz（TIM3 周期）
- ADC 采样率：10kHz，与注入电流相位同步
- 内阻测量周期：1 分钟
- 温度测量周期：30 秒
- 相位校准：补偿电路导致的电流-电压相位差
- 多点校准：使用实际电阻对测量值进行校正

### 测试和验收标准
- 通过 Keil 编译（0 Error, 0 Warning）
- 输出 `.hex` 和 `.axf` 文件
- 输出通讯协议设计方案
- 输出软件整体架构和模块划分文档

## Hardware Connection

### MCU / SoC
| 属性 | 值 |
|------|-----|
| 型号 | STM32G030F6P6 |
| 封装 | TSSOP-20 (6.4×4.4mm) |
| 内核 | ARM Cortex-M0+, 64MHz |
| Flash | 32KB |
| SRAM | 8KB (带硬件奇偶校验) |
| 调试接口 | SWD (SWCLK/SWDIO) |

### Debug / Flash Interface
| 协议 | 引脚 | 连接器 |
|------|------|--------|
| SWDIO | PA13 (pin 17) | H5 pin 3 (B-2100S04P-A110, 4-pin 2.54mm header) |
| SWCLK | PA14 (pin 18) | H5 pin 4 |
| 3.3V | VDD (pin 4) | H5 pin 1 |
| GND | VSS (pin 5) | H5 pin 2 |

### 供电
- **输入**：+12V (CN1/CN2, 2-pin 3.96mm接线端子)
- **稳压**：XC6206P332MR-G (U2-1, SOT-23-3) → 3.3V 输出
- **隔离侧**：CA-IS3721LS (U5, SOIC-8) 数字隔离器，隔离 UART 信号
- **模拟电源**：3.3VA 给运放和 ADC 前端供电
- **1.65V 基准**：由 TLV431AIDBZR (U1) + 电阻分压产生，给运放提供偏置

### Peripheral Wiring

以下信号从网表直接提取。MCU 引脚号对应 TSSOP-20 封装物理引脚。

| 信号名 | MCU 引脚 | 目标器件 | 方向 | 说明 |
|--------|---------|---------|------|------|
| UART1_RX | pin 1 (PB7) | CN3.3 → U5.3 (CA-IS3721) → 隔离侧RS485 | 输入 | 从机接收（主机模式）或主机接收（从机模式） |
| UART1_TX | pin 20 (PB3/PB4) | CN3.2 → U5.2 (CA-IS3721) → 隔离侧RS485 | 输出 | 从机发送（主机模式）或主机发送（从机模式） |
| $2N1217 | pin 2 (PB9) | CN3.1, U5.1 | I/O | UART1 经隔离器通讯 |
| UART2_RX | pin 10 | CN4.3 (R11串联10Ω) | 输入 | 级联从机接收（前一级主机发来） |
| UART2_TX | pin 9 | CN4.2 (R10串联10Ω) | 输出 | 级联从机发送（向下一级） |
| DQ | pin 11 | H6.2 (xh2_54-3p), R6 (4.7kΩ上拉) | 双向 | DS18B20 数据线 |
| M_S | pin 12 | R9 (100K上拉) | 输入 | 主从识别：低电平=主机，高电平=从机 |
| TIM3_CH3 | pin 15 (PB0) | R21 (100K) → RC滤波网络 | 输出 | 1kHz 50% 方波 → 正弦波生成 |
| VOLT_ADC | pin 8 (PA2) | R4-1(100k), R5-1(100k) 分压 | 输入 | 电池电压 ADC 采样 |
| CURRENT_ADC | pin 13 (PA7) | R52(100k), U11 | 输入 | 注入电流 ADC 采样（0.1Ω采样电阻R16） |
| RES_ADC | pin 14 | C24, R38, U10.7 | 输入 | 备用 ADC 通道 |
| NRST | pin 6 | U6 (C0603 100nF复位电容) | 输入 | 外部复位 |
| SWDIO | pin 17 (PA13) | H5.3 | 双向 | SWD 数据 |
| SWCLK | pin 18 (PA14) | H5.4 | 输入 | SWD 时钟 |

### 板上关键器件

| 器件 | 型号 | 功能 |
|------|------|------|
| U3-1 | STM32G030F6P6 | 主控 MCU (TSSOP-20) |
| U5 | CA-IS3721LS | 数字隔离器 (SOIC-8)，隔离 UART1 通讯 |
| OP1 | LM258DT | 双运放 (SOIC-8)，交流恒流驱动 |
| U1 | TLV431AIDBZR | 可调精密并联稳压器，产生 1.65V 偏置 |
| U1-1 | VPS8701B | 隔离电源模块 (SOT-23-6) |
| U2-1 | XC6206P332MR-G | 3.3V LDO (SOT-23-3) |
| T1-1 | VPT87DFB01B | 变压器 |
| Q1-Q4 | SS8050 | NPN 晶体管 (SOT-23-3) |
| R16 | 0.1Ω (0805) | 电流采样电阻 |
| D1 | SMAJ15CA | TVS 保护 |
| F1-1 | 0603L050YR | PTC 自恢复保险丝 |

### Power
| 供电轨 | 电压 | 来源 | 用途 |
|--------|------|------|------|
| +12V | 12V | CN1/CN2 | 系统总输入电源 |
| 5V | 5V | 经 U1-1 (VPS8701B) 隔离 | 隔离侧供电 |
| 5VA | 5V | 经 OP1 等 | 模拟电路供电 |
| 3.3V | 3.3V | XC6206P332MR-G LDO | MCU 数字供电 |
| 3.3VA | 3.3V | 经 LDO+滤波 | ADC 和模拟前端供电 |
| 1.65V | 1.65V | TLV431A + 电阻分压 | 运放偏置（虚拟地） |
| ISOGND | GND | 隔离地 | 所有隔离侧电路地 |

### Uncertainties

- pin 7 (PA0) 在网表中连接到 ISOGND，[推断] 可能是配置为输出低或内部下拉，用于指示隔离状态或作为 GPIO 控制。需确认实际用途。
- pin 3 (PC14/PC15) 未在网表中明确连接到 U3-1，[推断] 可能未使用或保留给外部晶振。
- pin 16 (PA11/PA12) 未在网表中明确连接到 U3-1，[推断] 可能未使用。
- U8 (SOP-8) 器件型号在 BOM 中未标注（仅显示 NaN），[推断] 根据连接可能是运算放大器或多路复用器。连接：U8.3→C9/R14/R23 (3N880), U8.1/U8.2→R13 (3N881), U8.5→R12/R13 (3N884), U8.6→R24/R25 (3N885), U8.7→D1/R15/R17/R22/R24 (3N886), U8.8→3.3V, U8.4→ISOGND。
- U9, U10, U11 (SOP-8) 器件型号在 BOM 中未标注。[推断] 根据连接（与 ADC 信号相关）可能是运放。U9 和 U10 连接与 ADC 信号链相关，U11 连接 CURRENT_ADC 信号。
- CN3/CN4 (xh2_54-4p) 是 UART 级联连接器，具体引脚分配需确认：CN3.1-4 连接到 UART1 和 U5 隔离器，CN4.1-4 连接 UART2 和电源/地。

## Build, Flash, And Run Notes

| 项目 | 值 |
|------|-----|
| 构建系统 | Keil MDK-ARM v5 (ArmClang V6.19) |
| 设备 | STM32G030F6Px |
| 项目文件 | `MDK-ARM/battery_re.uvprojx` |
| 构建命令 | `C:\Keil_v5\UV4\UV4.exe -j0 -b "MDK-ARM/battery_re.uvprojx" -o "MDK-ARM/build_log.txt"` |
| 刷新命令 | `pyocd flash -t stm32f103c8 build/firmware.elf`（注意：pyocd 目标设定为 stm32f103c8，与实际 STM32G030F6P6 不符，需修改）|
| 串口 | COM3, 115200 baud |
| 输出目录 | `MDK-ARM/battery_re/` |
| 输出文件 | `battery_re.axf`, `battery_re.hex` |
| 包含路径 | `../Core/Inc;../Drivers/STM32G0xx_HAL_Driver/Inc;../Drivers/STM32G0xx_HAL_Driver/Inc/Legacy;../Drivers/CMSIS/Device/ST/STM32G0xx/Include;../Drivers/CMSIS/Include;..\Drivers\CMSIS\DSP\Include` |
| 预定义宏 | `USE_HAL_DRIVER,STM32G030xx` |

### 启用的 HAL 模块
ADC、TIM、UART、DMA、GPIO、RCC、FLASH、PWR、EXTI、CORTEX、IWDG

### 时钟配置
- HSE = 8MHz（外部晶振）
- PLL: /1 * 16 /2 = 64MHz SysClk
- APB 不分频

### 已存在的源文件
| 文件 | 说明 |
|------|------|
| `Core/Src/system_stm32g0xx.c` | 系统初始化，64MHz 时钟配置 |
| `Core/Src/stm32g0xx_it.c` | 中断服务程序（含弱符号桩） |
| `Core/Src/stm32g0xx_hal_msp.c` | **不存在**（需新建）|
| `Core/Src/main.c` | **不存在**（需新建）|

### 中断向量使用情况（从 startup 和 it.c 推断）
| 中断 | Handler | 使用 |
|------|---------|------|
| SysTick | SysTick_Handler | HAL_IncTick + SCHED_IncTick |
| DMA1_Ch1 | DMA1_Channel1_IRQHandler | ADC DMA |
| ADC1 | ADC1_IRQHandler | ADC 转换完成 |
| TIM1_BRK_UP_TRG_COM | TIM1_BRK_UP_TRG_COM_IRQHandler | 映射到 htim3（注意：此映射可能有误）|
| TIM3 | TIM3_IRQHandler | TIM3 PWM/定时 |
| TIM14 | TIM14_IRQHandler | TIM14 定时 |
| USART1 | USART1_IRQHandler | UART1 接收中断 |
| USART2 | USART2_IRQHandler | UART2 接收中断 |

### 弱符号桩（供后续模块覆盖）
- `SCHED_IncTick(void)` — 调度器 1ms 滴答
- `UART_IRQHandler(uint32_t id)` — UART 中断处理（id=1 或 2）

## Constraints And Risks

### 关键约束
- MCU 仅有 TSSOP-20 封装，**17 个 GPIO**（含 SWD 和 NRST），资源紧张
- Flash 32KB，SRAM 8KB，代码空间有限
- 使用 Keil MDK-ARM V5 编译（ArmClang V6.19），**不能使用 GCC/CMake**
- 全部使用状态机，禁止阻塞/延时等待
- 需同时处理：PWM 生成、ADC 采样（10kHz + 相位同步）、DS18B20 时序（需软件模拟 OneWire）、双 UART 通讯、主从协议

### 缺失信息
- U8/U9/U10/U11 器件型号未在 BOM 中标明，无法确定其具体功能和驱动方式
- 交流恒流电路的具体 RC 滤波器参数未明确给出
- 自定义 UART 协议格式需自行设计
- 异常数据识别算法需自行设计

### 不确定的构建/刷新命令
- `flash_command` 中 pyocd 目标指定为 `stm32f103c8`，与实际 MCU STM32G030F6P6 不符，需要修改为 `stm32g030f6`
- 当前硬件配置使用 `pyocd flash`，但原始项目使用 Keil 调试器（UL2CM3.DLL）
- `host_test_command` 中的串口 COM7 与实际 COM3 不同

### 风险
- **相位同步**：ADC 采样需与注入电流相位同步（10kHz 采样，1kHz 信号），需要精确的定时器和触发配置
- **GPIO 不足**：TSSOP-20 仅有 17 个 GPIO，需要仔细分配
- **DS18B20 时序**：OneWire 协议需精确时序，在状态机中实现较为复杂
- **UART 级联协议**：需自定义可靠的主从分配和轮询协议
- **抗干扰**：充放电时逆变器/充电器会对测量产生干扰，需实现异常数据识别算法

## Confidence Assessment

| 章节 | 置信度 | 原因 |
|------|--------|------|
| 目标 | 高 | 用户需求明确，文档完整 |
| 任务要求 | 高 | user_req.txt 详细描述了所有功能和约束 |
| 硬件连接 | 中 | MCU 引脚分配来自网表（可靠），但部分器件型号缺失（U8-U11） |
| 构建和刷新 | 中 | 项目文件完整，构建已验证通过；但 flash 命令目标 MCU 型号错误 |
| 约束和风险 | 中 | 大部分约束明确，但部分硬件细节和协议设计需自行决定 |