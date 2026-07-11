Now I'll write the comprehensive context document based on all the evidence gathered.

```markdown
# Build Context

## Goal

电池内阻测量系统固件开发。目标硬件为 STM32G030F6P6 (TSSOP-20)，使用交流恒流注入法测量电池内阻：MCU 产生 1kHz 方波（TIM3_CH3, 占空比 50%），经 RC 滤波成正弦波、跟随器、运放产生恒流注入电池，同步采样电池两端电压（10kHz 采样率，与电流相位同步），计算内阻。同时每隔 1 分钟测量一次，DS18B20 每 30 秒测一次温度。多电池手拉手 UART 级联通讯：USART2 作为从机接收主机指令，USART1 作为主机向下一级从机发送指令。全部使用状态机，禁止阻塞。需设计异常数据识别算法应对充放电干扰。使用 Keil MDK-ARM (ArmClang V6.19) 编译。

## Source Materials

### Directory Overview

| Directory | Summary |
|-----------|---------|
| `battery_re/` | 目标工程目录，包含 Core、Drivers、MDK-ARM 子目录 |
| `battery_re/Core/Inc/` | 头文件：stm32g0xx_hal_conf.h（已启用 ADC/TIM/UART/DMA/IWDG/GPIO/RCC/PWR/FLASH/CORTEX/EXTI）, stm32g0xx_it.h |
| `battery_re/Core/Src/` | 源文件：stm32g0xx_it.c（含中断服务桩代码）, system_stm32g0xx.c |
| `battery_re/Drivers/` | STM32G0xx_HAL_Driver + CMSIS（含 DSP 库 arm_cortexM0l_math.lib） |
| `battery_re/MDK-ARM/` | Keil 项目文件 battery_re.uvprojx, 启动文件 startup_stm32g030xx.s, 各种构建日志 |
| `.document-reader/` | 网表、BOM、DS12991 数据手册的 Markdown/JSON 提取结果 |
| `.understand-anything/` | 中间分析产物（非关键） |

### Key Files Inspected

- `user_req.txt` — 用户需求文档：详细功能描述、引脚分配、编译命令、通讯协议要求
- `Netlist_Schematic1_2026-05-25.tel` — 网表文件：完整连接信息，MCU 引脚网络
- `.document-reader/netlist/document.md` — 网表 markdown 版
- `.document-reader/BOM/document.md` — BOM 物料清单 markdown 版
- `.document-reader/BOM_Board1_Schematic1_2026-05-23/document.md` — 第二份 BOM 清单（同上）
- `.document-reader/DS12991/document.md` — STM32G030x6/x8 数据手册内容（含 TSSOP20 引脚表）
- `battery_re/MDK-ARM/battery_re.uvprojx` — Keil 项目配置：MCU=STM32G030F6Px, Flash=64KB, RAM=8KB, 使用 ArmClang V6.19
- `battery_re/MDK-ARM/build_log.txt` — 上一次成功编译记录（0 Error, 0 Warning）
- `battery_re/Core/Src/stm32g0xx_it.c` — 中断服务：含 SCHED_IncTick, UART_IRQHandler 弱符号桩
- `battery_re/Core/Src/system_stm32g0xx.c` — 系统时钟配置：HSE 8MHz → PLL → 64MHz SysClk
- `battery_re/Core/Inc/stm32g0xx_hal_conf.h` — HAL 模块使能配置
- `battery_re/MDK-ARM/startup_stm32g030xx.s` — 启动文件：Stack=0x400, Heap=0x200

## Task Requirements

### Functional behavior

1. **交流恒流注入**: MCU 产生 1kHz 方波（占空比 50%），经外部 RC 滤波→正弦波→跟随器→运放→恒流注入电池
2. **电池内阻测量**: 同步采样电池两端电压（10kHz, 与电流相位同步），结合注入电流计算内阻；需校准电路导致的相位差
3. **定时测量**: 每 1 分钟测量一次内阻和电压
4. **温度测量**: DS18B20 每 30 秒测量一次温度，信号线 DQ
5. **多电池级联通讯**:
   - USART2（从机）接收上级主机指令
   - USART1（主机）向下级从机发送指令
   - 主机开机后为从机分配地址
   - 主机读取所有从机的电压、注入电流、内阻、温度等数据
   - 协议自定义
6. **主/从机判断**: 开机时检测 pin12（M_S 信号），内部上拉；若为低电平则为主机，否则为从机；判断后将引脚改为输入省电
7. **异常数据识别**: 充放电干扰下识别异常数据并丢弃，算法需精心设计
8. **多点校准**: 使用实际电阻对采集电压和真实内阻进行多点校准
9. **全部状态机实现**: 禁止阻塞，所有模块使用状态机

### Interfaces and protocols

- PWM 输出: TIM3_CH3 (1kHz, 50% duty)
- ADC 采样: 10kHz, 与电流相位同步
- UART1: 主机模式，向下一级从机发送指令
- UART2: 从机模式，接收上级主机指令
- 1-Wire: DS18B20 数据线 DQ
- 自定义级联通讯协议

### Tests and acceptance criteria

- 编译通过（0 Error, 0 Warning）
- 通过串口（COM3, 115200）观察运行状态
- 主机测试：`python host_tests/smoke_test.py --port COM7 --baud 115200`

## Hardware Connection

### MCU / SoC

| 项目 | 值 |
|------|-----|
| 型号 | STM32G030F6P6TR |
| 内核 | ARM Cortex-M0+ (64MHz max) |
| Flash | 64KB (0x08000000-0x0800FFFF) |
| SRAM | 8KB (0x20000000-0x20001FFF) |
| 封装 | TSSOP-20 (6.5×4.4mm) |
| 调试接口 | SWD (SWCLK/SWDIO) |

### Debug / Flash Interface

| 项目 | 值 |
|------|-----|
| 协议 | SWD (Serial Wire Debug) |
| 连接器 | H5 (HDR-TH_4P-P2.54-V-M, 4-pin 排针) |
| 引脚 | H5.1=3.3V, H5.2=ISOGND, H5.3=SWDIO, H5.4=SWCLK |
| 工具链 | pyOCD (`pyocd flash -t stm32f103c8 build/firmware.elf` — 注意：hardware_config 中的命令目标为 stm32f103c8，实际应为 stm32g030f6 或类似) |

### Peripheral Wiring

根据网表文件，MCU (U3-1, STM32G030F6P6 TSSOP-20) 引脚连接如下：

| 信号 | MCU 引脚# | MCU GPIO | 目标器件 | 方向 | 说明 |
|------|-----------|----------|---------|------|------|
| UART1_RX | 1 | [推断 PB7] | CN4.2 (R10.1)→UART 级联输入 | 输入 | USART1 从外部接收数据 |
| NC?/信号 | 2 | [推断 VDD/VDDA] | CN3.1, U5.2(CA-IS3721LS) | — | 隔离器通道 |
| ISOGND | 3 | — | 隔离地 | 电源 | 隔离侧地 |
| 3.3V | 4 | — | 电源 | 电源 | MCU 供电 |
| ISOGND | 5 | — | 隔离地 | 电源 | 隔离侧地 |
| NRST | 6 | NRST | U6.1(复位芯片?) | 输入 | 外部复位，上拉至 3.3V |
| ISOGND | 7 | — | 隔离地 | 电源 | 隔离侧地 |
| VOLT_ADC | 8 | [推断 PA2/PA3] | OP1 输出，分压网络 R4-1/R5-1 | 输入 | 电池电压 ADC 采样 |
| UART2_TX | 9 | [推断 PA2/USART2_TX] | U5.6(CA-IS3721LS)→隔离后输出 | 输出 | USART2 发送（作为从机） |
| UART2_RX | 10 | [推断 PA3/USART2_RX] | U5.7(CA-IS3721LS)→隔离后输入 | 输入 | USART2 接收（作为从机） |
| DQ | 11 | [推断 PB0/GPIO] | H6.2, R6.1(4.7kΩ 上拉至 3.3V) | 双向 | DS18B20 数据线 |
| M_S | 12 | [推断 PB1/GPIO] | R9.2(100kΩ 上拉至 3.3V) | 输入 | 主从选择：低=主机，高=从机 |
| CURRENT_ADC | 13 | [推断 PB0/ADC_IN8] | U11.1(运放输出), R52.2 | 输入 | 注入电流 ADC 采样 |
| RES_ADC | 14 | [推断 PB1/ADC_IN9] | U10.7(运放输出), C24.2, R38.2 | 输入 | 电池内阻相关 ADC 采样 |
| TIM3_CH3 | 15 | [推断 PB0/TIM3_CH3] | R21.1 → RC 滤波网络 | 输出 | 1kHz 50% 方波输出 |
| — | 16 | — | — | — | 未连接 |
| — | 17 | — | — | — | 未连接 |
| SWDIO | 18 | PA13 | H5.3 | 双向 | SWD 数据线 |
| SWCLK | 19 | PA14 | H5.4 | 输入 | SWD 时钟线 |
| UART1_TX | 20 | [推断 PB6/USART1_TX] | CN4.3 (R11.1)→UART 级联输出 | 输出 | USART1 发送（作为主机） |

**关键外围器件**:

| 器件 | 型号 | 功能 |
|------|------|------|
| U3-1 | STM32G030F6P6TR | 主控 MCU |
| U5 | CA-IS3721LS | 数字隔离器 (SOIC-8)，隔离 UART2 和部分信号 |
| U2-1 | XC6206P332MR-G | 3.3V LDO 稳压器 |
| U1-1 | VPS8701B | 电源相关 (SOT-23-6) |
| OP1 | LM258DT | 双运放，用于电压/电流信号调理 |
| U1 | TLV431AIDBZR | 可调精密并联稳压器 (1.25V 基准) |
| U8,U9,U10,U11 | SOP-8 (未标型号) | 运放或模拟开关，用于信号调理 |
| Q1-Q4 | SS8050 | NPN 晶体管 |
| T1-1 | VPT87DFB01B | 变压器（隔离电源） |
| D1-1 | SMAJ15CA | TVS 保护 |
| R16 | 0.1Ω (0805) | 采样电阻 |
| H6 | xh2_54-3p | DS18B20 连接器 (DQ, 3.3V, GND) |
| H5 | 4-pin 排针 | SWD 调试接口 |

### Power

| 项目 | 值 |
|------|-----|
| 输入电源 | +12V (CN1, CN2) |
| 隔离侧电源 | 5V, 5VA, 3.3VA (隔离变压器 T1 + VPS8701B) |
| MCU 供电 | 3.3V (XC6206P332MR-G LDO 输出) |
| 非隔离侧 | 3.3V, 1.65V (分压) |
| 地平面 | GND（非隔离侧）, ISOGND（隔离侧，通过 U5 隔离器隔离） |

## Uncertainties

- MCU TSSOP20 引脚号到 GPIO 端口/引脚的具体映射未从 datasheet 中找到完整清晰的表格，[推断]基于标准 STM32G030F6P6 引脚排列，但 UART1 信号（TSSOP20 pin1=RX, pin20=TX）暗示使用了 PB7(RX)/PB6(TX) 的 AF0 功能而非 PA9/PA10（因 TSSOP20 无 PA9/PA10）
- U8/U9/U10/U11 (SOP-8) 器件型号未标注，其具体功能需从电路拓扑推断
- U6/U7 (C0603 电容) — 标注为电容但设计符以 U 开头，可能为复位 IC 或其他小封装器件
- CURRENT_ADC / RES_ADC / VOLT_ADC 三个 ADC 通道的具体 GPIO 端口/ADC_IN 通道号未在网表中直接标明，需结合电路分析确认
- `hardware_config` 中 flash 命令目标为 `stm32f103c8`，与实际 MCU STM32G030F6P6 不符，需修正为 `stm32g030f6p6` 或类似
- 网表中 U6.1 与 NRST 相连，U6 可能为复位监控芯片而非电容

## Build, Flash, And Run Notes

| 项目 | 值 |
|------|-----|
| 工具链 | Keil MDK-ARM V5, ArmClang V6.19 |
| 编译器路径 | `C:\Keil_v5\UV4\UV4.exe` |
| 项目文件 | `MDK-ARM/battery_re.uvprojx` |
| 预定义宏 | `USE_HAL_DRIVER,STM32G030xx` |
| 包含路径 | `../Core/Inc;../Drivers/STM32G0xx_HAL_Driver/Inc;../Drivers/STM32G0xx_HAL_Driver/Inc/Legacy;../Drivers/CMSIS/Device/ST/STM32G0xx/Include;../Drivers/CMSIS/Include;..\Drivers\CMSIS\DSP\Include` |
| 已启用 HAL 模块 | ADC, TIM, UART, IWDG, DMA, GPIO, EXTI, RCC, FLASH, PWR, CORTEX |
| 构建命令 | `UV4.exe -j0 -b "MDK-ARM/battery_re.uvprojx" -o "MDK-ARM/build_log.txt"`（或 `uv4.exe -j0 -r ...` 全量重建） |
| 系统时钟 | HSE 8MHz → PLL (×16, ÷2) → 64MHz SysClk |
| Flash 等待周期 | 2 WS (64MHz > 48MHz) |
| 退码含义 | 0=成功, 1=有 warning, 2-20=编译 error, 21+=fatal |
| 输出文件 | `battery_re/battery_re.axf`, `battery_re/battery_re.hex` |
| 调试/烧录 | pyOCD（需修正 target 为 `stm32g030f6`） |
| 串口观察 | COM3, 115200 baud |
| 主机测试 | `python host_tests/smoke_test.py --port COM7 --baud 115200` |

**现有源文件列表**（Keil 项目中已包含）:

| 分组 | 文件 |
|------|------|
| Application/MDK-ARM | startup_stm32g030xx.s |
| Application/User/Core | main.c（尚不存在，需创建）, stm32g0xx_it.c, stm32g0xx_hal_msp.c（尚不存在，需创建） |
| Drivers/STM32G0xx_HAL_Driver | hal_adc.c, hal_adc_ex.c, ll_adc.c, hal_rcc.c, hal_rcc_ex.c, ll_rcc.c, hal_flash.c, hal_flash_ex.c, hal_gpio.c, hal_dma.c, hal_dma_ex.c, hal_pwr.c, hal_pwr_ex.c, hal_cortex.c, hal.c, hal_exti.c, hal_iwdg.c, hal_tim.c, hal_tim_ex.c, hal_uart.c, hal_uart_ex.c |
| Drivers/CMSIS | system_stm32g0xx.c, arm_cortexM0l_math.lib |

## Constraints And Risks

- **main.c 和 stm32g0xx_hal_msp.c 尚不存在** — 需从头创建，已存在的 stm32g0xx_it.c 中包含 SCHED_IncTick 和 UART_IRQHandler 弱符号桩
- **UART 引脚映射不确定** — TSSOP20 封装下 USART1 可能映射到 PB6(TX)/PB7(RX)（AF0），而非标准 PA9/PA10；USART2 可能在 PA2(TX)/PA3(RX)
- **ADC 通道映射不确定** — 三个 ADC 信号 (VOLT_ADC, CURRENT_ADC, RES_ADC) 对应的具体 ADC_IN 通道号需根据 GPIO 映射确认
- **flash 命令目标错误** — hardware_config 中指定 `stm32f103c8`，应改为 `stm32g030f6` 或 `stm32g030f6p6`
- **通讯协议待定义** — 用户要求自定义 UART 级联协议，需设计帧格式、地址分配、数据读取命令等
- **相位校准算法** — 需对 RC 滤波和模拟电路引入的电流-电压相位差进行软件校准
- **异常数据识别算法** — 要求精心设计以应对充放电干扰，无具体指标
- **DS18B20 时序** — 1-Wire 协议需精确时序，在 64MHz 主频下需注意延时实现
- **所有模块用状态机** — 禁止 HAL_Delay 等阻塞调用，所有定时需基于 SysTick 或硬件定时器
- **10kHz ADC 采样与 1kHz PWM 同步** — ADC 触发需与 TIM3 同步，每个 PWM 周期采样 10 点
- **SRAM 仅 8KB** — 需注意内存使用

## Confidence Assessment

| Section | Confidence | Reason |
|---------|-----------|--------|
| Goal | High | 用户需求明确，描述了完整的电池内阻测量系统功能 |
| Task Requirements | High | user_req.txt 提供了详细的功能要求和实现步骤 |
| Hardware Connection | Medium | 网表提供了完整的 MCU 引脚网络，但 MCU GPIO 到引脚号的映射（TSSOP20）需参考数据手册推断，部分外围器件型号未标注 |
| Build & Flash | High | uvprojx 构建配置完整，构建日志显示上次编译成功；但 flash 命令目标需修正 |
| Constraints & Risks | High | 明确识别了 main.c/HAL_MSP 缺失、引脚映射不确定性、协议待定义等关键风险 |
```