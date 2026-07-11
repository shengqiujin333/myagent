Now I have enough information to write the comprehensive context.md.

```markdown
# Build Context

## Goal

完成电池内阻测量系统的固件开发。项目目标是在STM32G030F6P6 (TSSOP-20) MCU上实现电池内阻测量功能，核心原理为：MCU产生1kHz、50%占空比方波 → 通过RC滤波器形成正弦波 → 经过跟随器和运放产生交流恒流注入电池 → 采集电池两端电压和注入电流，计算电池内阻。每隔1分钟测量一次。

系统支持多电池手拉手级联，通过UART1(主机)与下一级从机通信，UART2(从机)接收上一级主机指令。支持DS18B20温度测量(30s一次)。使用逻辑状态机实现，整体禁止阻塞。

## Source Materials

### Directory Overview

| Directory | Summary |
|-----------|---------|
| `battery_re/` | 主项目目录，包含Keil MDK-ARM工程文件、STM32G0xx HAL驱动、CMSIS库、Core源文件 |
| `battery_re/Core/Inc/` | HAL配置头文件(stm32g0xx_hal_conf.h)、中断头文件 |
| `battery_re/Core/Src/` | 现有源文件: stm32g0xx_it.c, system_stm32g0xx.c (main.c和stm32g0xx_hal_msp.c待创建) |
| `battery_re/Drivers/STM32G0xx_HAL_Driver/` | STM32G0xx HAL驱动库(ADC, TIM, UART, DMA, GPIO, RCC, PWR, FLASH, IWDG, EXTI等) |
| `battery_re/Drivers/CMSIS/` | CMSIS核心、DSP库(包含arm_cortexM0l_math.lib已链接)、Device文件 |
| `battery_re/MDK-ARM/` | Keil工程文件(battery_re.uvprojx)、启动文件(startup_stm32g030xx.s)、构建脚本(battery_re.BAT)、构建日志 |
| `.document-reader/BOM_Board1_Schematic1_2026-05-23/` | BOM物料清单(Markdown格式) |
| `.document-reader/DS12991/` | STM32G030x6/x8数据手册(分块Markdown) |
| `.document-reader/netlist/` | 网表文件(Markdown格式)，描述所有网络连接 |

### Key Files Inspected

- `user_req.txt` — 用户需求文档，描述了全部功能要求和实现步骤
- `Netlist_Schematic1_2026-05-25.tel` — 原始网表文件，定义了所有电气连接
- `.document-reader/netlist/document.md` — 网表Markdown版，显示所有网络和元器件引脚连接
- `.document-reader/BOM_Board1_Schematic1_2026-05-23/document.md` — BOM清单，包含所有元器件型号、封装、供应商
- `.document-reader/DS12991/chunks/chunk_0034.md` — STM32G030Fx TSSOP20引脚图和引脚分配表
- `.document-reader/DS12991/chunks/chunk_0037.md` — TSSOP20引脚详细功能描述
- `.document-reader/DS12991/chunks/chunk_0040.md` — 端口A/B复用功能映射
- `battery_re/MDK-ARM/battery_re.uvprojx` — Keil uVision项目文件，指定设备STM32G030F6Px、编译器V6.19(ARMCLANG)
- `battery_re/MDK-ARM/build.log` — 上次成功编译日志(0 Error, 0 Warning)
- `battery_re/MDK-ARM/startup_stm32g030xx.s` — 启动文件，Stack=0x400, Heap=0x200
- `battery_re/Core/Inc/stm32g0xx_hal_conf.h` — HAL配置：启用ADC、TIM、UART、DMA、GPIO、EXTI、IWDG、RCC、FLASH、PWR、CORTEX模块
- `battery_re/Core/Src/stm32g0xx_it.c` — 中断服务程序，定义弱符号SCHED_IncTick和UART_IRQHandler
- `battery_re/Core/Src/system_stm32g0xx.c` — 系统初始化，SystemCoreClock=64MHz，HSE 8MHz→PLL→64MHz

### Task Requirements

**功能行为：**
- MCU产生1kHz、50%占空比方波(PWM)，经RC滤波→正弦波→跟随器→运放产生交流恒流，注入电池
- 采样电阻100mΩ(R16, 0.1Ω/0805)，用于测量注入电流
- 采集电池两端电压(VOLT_ADC)和注入电流(CURRENT_ADC)
- 通过电压和电流计算电池内阻
- 每1分钟测量一次内阻
- DS18B20温度测量，30s一次
- 多电池级联：UART2作为从机接收上级主机指令，UART1作为主机与下级从机通信
- 主机通过pin12(M_S)检测主从身份：上拉后若为低电平则为主机，否则为从机；开机判断一次后改为输入
- 主机给从机分配地址，定时读取所有从机数据(电压、内阻、温度等)
- 10kHz同步采样(与电流相位同步)
- 对电路导致的注入电流与电压的相位差进行校正
- 支持使用实际电阻进行多点校准
- 异常数据识别算法(抗充电/放电干扰)
- 全状态机实现，禁止阻塞

**接口和协议：**
- UART1: 主机TX(向下级从机)，与从机通信，波特率待定
- UART2: 从机RX(接收上级主机)，与主机通信，波特率待定
- 自定义UART级联通信协议，主机分配地址，读取所有从机数据
- DS18B20: 单总线(1-Wire)协议

**输出和指示：**
- [推断] 通过UART输出测量数据(无指示器件在BOM/BOM中未见LED等)

**时序和性能：**
- PWM: 1kHz, 50%占空比 (TIM3_CH3)
- ADC采样: 10kHz，与电流相位同步
- 内阻测量周期: 1分钟
- 温度测量周期: 30秒
- 主频: 64MHz (HSE 8MHz → PLL)

**测试和验收标准：**
- 通过Keil编译(0 Error, 0 Warning)
- 编译命令: `UV4.exe -j0 -b "MDK-ARM/battery_re.uvprojx" -o "MDK-ARM/build_log.txt"`
- 需要输出通讯协议设计方案
- 需要输出软件整体架构、模块划分、设计方案
- 设计文件和文档同样重要

## Hardware Connection

### MCU / SoC

| 项目 | 值 |
|------|-----|
| Part number | STM32G030F6P6TR |
| Core / architecture | Arm Cortex-M0+, 32-bit, up to 64MHz |
| Package | TSSOP-20 (6.5×4.4mm, 0.65mm pitch) |
| Flash | 32KB |
| SRAM | 8KB (with HW parity) |
| Datasheet | DS12991 Rev 6 |
| Reference Manual | RM0454 |

### Debug / Flash Interface

| 项目 | 值 |
|------|-----|
| 协议 | SWD (Serial Wire Debug) |
| 连接器 | H5 (4-pin header, B-2100S04P-A110, 2.54mm pitch) |
| SWCLK | H5.4 → MCU Pin 19 (PA15/PA14-BOOT0) |
| SWDIO | H5.3 → MCU Pin 18 (PA13) |
| NRST | H5.2 → MCU Pin 6 (NRST) |
| GND | H5.1 → GND |
| 所需工具 | J-Link, ST-Link 等支持SWD的调试器 |
| Keil调试器配置 | UL2CM3.DLL, 使用STM32G0xx_32.FLM |

### Peripheral Wiring

| 信号 | MCU引脚 | 目标器件/模块 | 方向 | 说明 |
|------|---------|--------------|------|------|
| **UART1_TX** | Pin 20 (PB3/PB4/PB5/PB6) → 通过R10(10Ω) → CN4.3 | CN4 (xh2.54-4p) 级联接口 | 输出 | 主机TX，向下级从机发送指令 |
| **UART1_RX** | Pin 1 (PB7/PB8) → 通过R11(10Ω) → CN4.2 | CN4 (xh2.54-4p) 级联接口 | 输入 | 主机RX，接收下级从机数据 |
| **UART2_TX** | Pin 9 (PA2) → 通过R8(10Ω) → U5.6 | U5 (CA-IS3721LS) 隔离器 | 输出 | 从机TX，向上级主机发送数据 |
| **UART2_RX** | Pin 10 (PA3) → 通过R7(10Ω) → U5.7 | U5 (CA-IS3721LS) 隔离器 | 输入 | 从机RX，接收上级主机指令 |
| **DQ** | Pin 11 (PA4) → R6(4.7kΩ)上拉 → H6.2 | H6 (xh2.54-3p) → DS18B20数据线 | 双向 | 1-Wire协议，30s测量一次温度 |
| **M_S** | Pin 12 (PA5) → R9(100K) | 主从检测引脚 | 输入 | 开机内部上拉后读电平：低=主机，高=从机 |
| **TIM3_CH3** | Pin 15 (PB0/PB1/PB2/PA8) → R21(100K) | PWM输出到RC滤波电路 | 输出 | 1kHz, 50%占空比方波 |
| **CURRENT_ADC** | Pin 13 (PA6) → R52(100kΩ) → U11.2 | 电流测量ADC输入 | 输入 | 采样电阻R16(100mΩ)两端电压经运放 |
| **RES_ADC** | Pin 14 (PA7) → R38(10kΩ) → C24(1nF) → U10.7 | 电阻/电压测量ADC输入 | 输入 | 电池两端电压经调理 |
| **VOLT_ADC** | Pin 8 (PA1) → R4-1(100kΩ)/R5-1(100kΩ)分压 | 电池电压ADC输入 | 输入 | 分压后测量电池电压 |
| **NRST** | Pin 6 (NRST) → U6.1 (100nF电容到GND) | 复位 | 输入 | 外部复位，带电容去耦 |
| **SWCLK** | Pin 19 (PA15/PA14-BOOT0) → H5.4 | SWD时钟 | 输入 | 调试接口 |
| **SWDIO** | Pin 18 (PA13) → H5.3 | SWD数据 | 双向 | 调试接口 |
| **VDD/VDDA** | Pin 4 | 3.3V电源 | 输入 | 3.3V供电 |
| **VSS/VSSA** | Pin 5 | GND | - | 地 |
| **PA0** | Pin 7 | GND (网表中连接到GND) | - | [推断] 可能作为GND或未使用，根据数据手册Note 3，PA0/PA1/PA2在SO8N封装中与NRST绑定，低电平会触发复位；但TSSOP20中PA0是独立引脚，此处连到GND可能有问题 |

**网表确认的额外连接：**

| 信号 | 连接 | 说明 |
|------|------|------|
| 3.3V | MCU Pin 4, U2-1(3.3V LDO), U5.8(隔离器), U8.8等 | 主电源 |
| 3.3VA | Q1.3, Q3.3, U9.8, U10.8, U11.8等 | 模拟电源(经隔离) |
| 5V | U2-1.3(5V输入到LDO), D2-1, D3-1等 | 5V电源输入 |
| +12V | CN1/CN2, U1-1.5(VPS8701B电源芯片) | 12V电源输入 |
| ISOGND | 隔离侧地，连接U5(隔离器)、U8/U9/U10/U11(运放)等 | 隔离地 |
| 1.65V | R3(660Ω)/R4(820Ω)分压，U1(TLV431)基准 | 1.65V虚拟地/基准 |

### 关键外设器件

| 器件 | 型号/值 | 功能 |
|------|---------|------|
| MCU | STM32G030F6P6 (TSSOP-20) | 主控制器 |
| LDO | XC6206P332MR-G (SOT-23-3) | 3.3V稳压 (U2-1) |
| 隔离器 | CA-IS3721LS (SOIC-8) | UART隔离 (U5) |
| 运放1 | LM258DT (SOIC-8) | 信号调理 (OP1) |
| 运放组 | SOP-8 ×4 (U8/U9/U10/U11) | 信号调理，具体型号待确认 |
| 采样电阻 | 100mΩ (0805) (R16) | 电流采样 |
| 温度传感器 | DS18B20 (通过H6连接) | 温度测量 |
| 电源芯片 | VPS8701B (SOT-23-6) (U1-1) | 隔离电源转换 |
| 基准 | TLV431AIDBZR (SOT-23-3) (U1) | 1.25V基准 |
| 变压器 | VPT87DFB01B (T1-1) | 隔离电源变压器 |
| TVS | SMAJ15CA (D1-1) | 15V瞬态抑制 |
| PTC | 0603L050YR (F1-1) | 500mA自恢复保险丝 |

### Power

| 项目 | 值 |
|------|-----|
| MCU供电电压 | 3.3V (通过XC6206P332MR-G从5V稳压) |
| 模拟供电 | 3.3VA (隔离侧，由VPS8701B隔离电源模块产生) |
| 系统输入 | +12V (通过CN1/CN2接入) |
| LDO | XC6206P332MR-G, 3.3V输出, SOT-23-3 |
| 隔离电源 | VPS8701B + VPT87DFB01B变压器，产生隔离5V/3.3VA |
| 虚拟地 | 1.65V (TLV431基准 + 电阻分压) |

### Uncertainties

- PA0 (Pin 7)在网表中连接到GND网络；但根据DS12991表12注3，在SO8N封装中PA0/PA1/PA2与NRST绑定，低电平会触发复位。但在TSSOP-20中PA0是独立引脚。如果PA0确实被拉低到GND，可能会引起问题。建议确认原理图设计意图。
- UART1的具体引脚功能：Pin 1 (PB7/PB8)和Pin 20 (PB3/PB4/PB5/PB6)是多功能引脚，需要根据AF配置确定具体是哪个GPIO。USART1的TX可映射到PB6(AF0)，RX可映射到PB7(AF0)。
- U8/U9/U10/U11运放型号在BOM中未指定具体型号（SOP-8封装，未填制造商），需要确认。
- CN3(4P)级联接口的完整信号定义：从网表看CN3.1→U5.1, CN3.2→U5.2, CN3.3→U5.3, CN3.4→U3.1(UART1_RX)，可能包含UART信号和电源。
- UART波特率在需求中未明确指定，需要自定义协议时确定。

## Build, Flash, And Run Notes

| 项目 | 值 |
|------|-----|
| **Build system** | Keil MDK-ARM (uVision) |
| **IDE** | Keil uVision V5, 路径: `C:\Keil_v5\UV4\UV4.exe` |
| **Toolchain** | ARMCLANG V6.19 (AC6) |
| **Device** | STM32G030F6Px |
| **Pack** | Keil.STM32G0xx_DFP.1.4.0 |
| **编译命令** | `UV4.exe -j0 -b "MDK-ARM/battery_re.uvprojx" -o "MDK-ARM/build_log.txt"` |
| **全量重建** | `UV4.exe -j0 -r "MDK-ARM/battery_re.uvprojx" -o "MDK-ARM/build_log.txt"` |
| **CPU配置** | IRAM(0x20000000, 0x2000) IROM(0x08000000, 0x10000) Cortex-M0+ |
| **预定义宏** | `USE_HAL_DRIVER, STM32G030xx` |
| **包含路径** | `../Core/Inc; ../Drivers/STM32G0xx_HAL_Driver/Inc; ../Drivers/STM32G0xx_HAL_Driver/Inc/Legacy; ../Drivers/CMSIS/Device/ST/STM32G0xx/Include; ../Drivers/CMSIS/Include; ..\Drivers\CMSIS\DSP\Include` |
| **链接库** | `..\Drivers\CMSIS\DSP\Lib\ARM\arm_cortexM0l_math.lib` (CMSIS DSP库) |
| **输出目录** | `battery_re\` |
| **输出文件** | `battery_re.axf` (ELF), `battery_re.hex` (Intel HEX) |
| **串口观察** | [推断] 通过UART1或UART2输出数据，波特率待定 |
| **工作目录** | `C:\Users\123\Desktop\neizu\tasknew\battery_re` |
| **所需工具** | Keil MDK-ARM V5 (含ARMCLANG V6.19), ST-Link/J-Link调试器 |
| **Stack大小** | 0x400 (1024 bytes) |
| **Heap大小** | 0x200 (512 bytes) |

**退出码说明：**
- 0: 成功 (0 error, 0 warning)
- 1: 有warning但无error (仍算通过)
- 2-20: 编译error
- 21+: fatal error

## Constraints And Risks

**缺失信息：**
- UART波特率未指定，需在协议设计时确定
- U8/U9/U10/U11具体运放型号未知
- ADC参考电压配置未明确（VREF+在LQFP48有独立引脚，但TSSOP20无VREF+引脚，内部连接到VDDA）
- 相位校正的具体算法未指定
- 异常数据识别算法的具体标准未指定

**不清晰的硬件细节：**
- PA0 (Pin 7)连接到GND的可能性与数据手册注3的潜在冲突
- 电池连接器H1/H2/H3/H4(battery_pin)的具体功能分配
- CN3(4P)级联接口的信号定义需要从网表进一步分析

**编译/烧录不确定性：**
- 需要确保Keil MDK-ARM V5已安装且包含STM32G0xx_DFP.1.4.0包
- `-j0`参数抑制对话框，但如果编译失败需要查看日志文件

**不完整的验收标准：**
- 无具体的测试用例或测试方法
- 内阻测量精度要求未指定
- 通信协议的鲁棒性验证标准未指定

**真实硬件验证风险：**
- 电池充放电环境下的干扰可能影响测量
- 相位同步要求在10kHz采样率下精度较高
- 多电池级联通信的时序和冲突处理

## Confidence Assessment

| Section | Confidence | Reason |
|---------|-----------|--------|
| Goal | High | 用户需求文档清晰描述了所有功能和目标 |
| Task Requirements | High | 需求文档详细列出了所有功能点，从PWM生成到通信协议 |
| Hardware Connection | Medium | 网表提供了完整连接信息，但PA0接地可能存在问题，运放型号不明确 |
| Build & Flash | High | Keil项目文件完整且已验证可编译，编译命令明确 |
| Constraints & Risks | Medium | 主要风险和缺失信息已识别，但部分硬件细节需要原理图确认 |
```