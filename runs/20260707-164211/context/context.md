以下是 `context.md` 文档：

```markdown
# 构建上下文 — 电池内阻测量系统

## Goal

为 STM32G030F6P6 (TSSOP-20) 开发嵌入式固件，实现电池内阻测量、温度监测（DS18B20）、以及多电池手拉手 UART 级联通信。项目基于 Keil MDK-ARM (ArmClang V6.19) 构建，输出路径为 `battery_re/`。

核心功能：
- PWM (1kHz, 50% 占空比) → RC 滤波 → 正弦波 → 恒流驱动注入电池
- ADC 同步采集注入电流和电池两端电压，计算内阻
- 每 N 分钟自动测量一次
- DS18B20 每 30s 测温
- 多电池 UART 级联：主机↔从机（自定义协议，地址分配，汇总数据）
- UART1 隔离通信，UART2 隔离接收
- 全部基于状态机，禁止阻塞

## Source Materials

| 文件/目录 | 说明 |
|---|---|
| `user_req.txt` | 用户需求：功能描述、引脚分配、协议要求 |
| `.document-reader/netlist/document.md` | 原理图网表：所有信号连接、MCU 引脚对应关系 |
| `.document-reader/netlist/chunks/chunk_0001~0003.md` | 网表分块（完整信号列表） |
| `.document-reader/BOM/document.md` | BOM：元器件列表、封装、厂家 |
| `.document-reader/BOM_Board1_Schematic1_2026-05-23/document.md` | 板级 BOM |
| `.document-reader/DS12991/document.md` + chunks (29~41) | STM32G030x6/x8 数据手册：引脚定义、AF 映射、电气特性 |
| `battery_re/MDK-ARM/battery_re.uvprojx` | Keil 项目文件：已注册文件、编译选项、设备配置 |
| `battery_re/Core/Inc/stm32g0xx_hal_conf.h` | HAL 模块使能配置 |
| `battery_re/Core/Inc/stm32g0xx_it.h` | 中断声明（包含已规划的外设中断） |
| `battery_re/Core/Src/stm32g0xx_it.c` | 现有中断处理（弱符号桩） |
| `battery_re/Core/Src/system_stm32g0xx.c` | 系统时钟：HSE 8MHz → PLL → 64MHz SysClk |
| `battery_re/MDK-ARM/startup_stm32g030xx.s` | 启动文件 + 中断向量表 |
| `Netlist_Schematic1_2026-05-25.tel` | 原始网表文件 |

## Task Requirements

### 功能性行为
- 产生 1kHz 50% 占空比方波 → RC 滤波成正弦波 → 通过运放实现交流恒流注入电池
- 10kHz 同步采样（与注入电流相位同步），测量电池两端电压和注入电流
- 计算电池内阻（R = V/I）
- 对电路导致的注入电流与电压相位差进行校正
- 支持实际电阻多点校准
- 每 N 分钟自动测量一次（N 可配置）
- DS18B20 每 30s 测一次温度
- 异常数据识别算法（抗充电/放电干扰）

### 通信接口和协议
- **UART1**（主机端，隔离）：作为主机与下一个电池从机通信，发送指令
- **UART2**（从机端，隔离）：作为从机接收前面主机的指令
- **自定义协议**：主机分配地址，主机获取所有从机的数据（电压、电流、内阻、温度等）

### 主/从识别
- MCU Pin 12 (M_S)：开机判断主/从
  - 内部上拉后，若 Pin 12 = 低电平 → 主机
  - 若 Pin 12 = 高电平 → 从机
  - 判断后改为输入模式省电

### 输出和指示
- UART 通信数据（隔离后通过 CN3/CN4 连接器输出）
- ADC 数据用于内部运算

### 时序和性能
- PWM: 1kHz (1ms 周期)
- ADC 采样: 10kHz (100µs 周期)，与注入电流相位同步
- DS18B20: 30s 测量间隔
- 内阻测量: 每 N 分钟一次（N 可配置）
- 全部基于状态机，禁止阻塞

### 测试和验收标准
- 可通过 Keil 编译（UV4.exe -j0 -b），无 error
- 输出正确的内阻测量值
- 主机/从机通过 UART 级联通信正常
- DS18B20 温度读取正常

## Hardware Connection

### MCU / SoC

| 参数 | 值 |
|---|---|
| 型号 | STM32G030F6P6TR (U3-1) |
| 内核 | Arm Cortex-M0+，最高 64 MHz |
| Flash | 64 KB (0x08000000~0x0800FFFF) |
| SRAM | 8 KB (0x20000000~0x20001FFF) |
| 封装 | TSSOP-20 (6.5×4.4 mm) |
| 调试 | SWD (SWCLK + SWDIO) |

### Debug / Flash Interface
- **协议**: SWD (Serial Wire Debug)
- **连接器**: H5 (B-2100S04P-A110, 2.54mm 4Pin 排针)
- **引脚**: H5.3=SWDIO(PA13), H5.4=SWCLK(PA14), H5.1=3.3V, H5.2=GND
- **工具**: pyocd / JLink / ST-Link

### Peripheral Wiring

#### MCU 引脚连接（从网表提取）

| 信号名称 | 网表引脚 | MCU Pin# | 目标器件 | 方向 | 备注 |
|---|---|---|---|---|---|
| UART1_RX | U3-1.1 | 1 (PB7) | CN3.4, U5.4 (CA-IS3721LS 隔离器) | 输入 | 隔离后来自前级从机 |
| (连接 CN3.1) | U3-1.2 | 2 | CN3.1, U5.1 | 双向 | 经隔离器到连接器 |
| 3.3V (VDD) | U3-1.4 | 4 | 电源 | 供电 | XC6206P332MR 稳压输出 3.3V |
| GND (ISOGND) | U3-1.5 | 5 | 隔离地 | 供电 | |
| NRST | U3-1.6 | 6 | U6.1 (复位) | 输入 | 外部复位 |
| GND (ISOGND) | U3-1.7 | 7 | 隔离地 | 供电 | |
| VOLT_ADC | U3-1.8 | 8 (PA1) | C5-1.1, R4-1.2, R5-1.1 | 输入 | ADC_IN1：电池电压采样 |
| UART2_TX | U3-1.9 | 9 (PA2) | R8.1, U5.6 (隔离器) | 输出 | 发往前级主机 |
| UART2_RX | U3-1.10 | 10 (PA3) | R7.1, U5.7 (隔离器) | 输入 | 从前级主机接收 |
| DQ | U3-1.11 | 11 (PA4) | H6.2, R6.1 (4.7kΩ 上拉) | 双向 | DS18B20 单总线 |
| M_S | U3-1.12 | 12 (PA5) | R9.2 (100kΩ) | 输入 | 主/从选择（开机判断） |
| CURRENT_ADC | U3-1.13 | 13 (PA6) | R52.2, U11.1 | 输入 | ADC_IN6：注入电流采样 |
| RES_ADC | U3-1.14 | 14 (PA7) | C24.2, R38.2, U10.7 | 输入 | ADC_IN7：内阻测量 |
| TIM3_CH3 | U3-1.15 | 15 (PB0) | R21.1 (100kΩ) | 输出 | PWM 输出 (1kHz, 50%) |
| SWDIO | U3-1.18 | 18 (PA13) | H5.3 | 双向 | 调试接口 |
| SWCLK | U3-1.19 | 19 (PA14) | H5.4 | 输入 | 调试接口 |
| UART1_TX | U3-1.20 | 20 (PB6) | R10.1, CN4.3 (隔离器侧) | 输出 | 发往下一级从机 |

#### [推断] MCU 引脚与 GPIO 的对应关系

[推断] 基于 STM32G030F6P6 TSSOP-20 封装数据手册表 12 和网表信号名：
- USART1_RX 在 PB7 (Pin 1, AF0), USART1_TX 在 PB6 (Pin 20, AF0)
- USART2_TX 在 PA2 (Pin 9, AF1), USART2_RX 在 PA3 (Pin 10, AF1)
- TIM3_CH3 在 PB0 (Pin 15, AF1) — 输出 PWM 给 RC 滤波电路
- ADC_IN1(PA1)/ADC_IN6(PA6)/ADC_IN7(PA7) 分别对应 VOLT_ADC/CURRENT_ADC/RES_ADC
- M_S(PA5) 为数字输入，DS18B20 DQ(PA4) 为开漏双向

**注意**：PA0 (Pin 7) 在网表中连接 ISOGND，但数据手册指出在 SO8N 封装中 PA0/NRST 共用引脚。TSSOP20 中 PA0 在 pin 7，该引脚在原理图中直接接地。

### 关键外设 IC

| 器件 | 型号 | 功能 |
|---|---|---|
| U1 | TLV431AIDBZR | 可调精密并联稳压器（产生 1.65V 参考电压） |
| U1-1 | VPS8701B | 隔离电源模块（SOT-23-6） |
| U2-1 | XC6206P332MR-G | 3.3V LDO 稳压器 |
| U5 | CA-IS3721LS | 双通道数字隔离器 (SOIC-8)，用于 UART 隔离通信 |
| OP1 | LM258DT | 双运放 (SOIC-8)，用于信号调理 |
| U8,U9,U10,U11 | SOP-8 (未标型号) | 运放/模拟处理（可能是 LMV 系列运放） |
| Q1~Q4 | SS8050 | NPN 三极管，用于开关/驱动 |
| T1-1 | VPT87DFB01B | 变压器，隔离电源 |
| D1 | SMAJ15CA | TVS 管，15V 双向保护 |
| D2-1,D3-1 | RB160M-30 | 肖特基二极管，30V/1A |

### 电源

| 电源轨 | 电压 | 来源 | 用途 |
|---|---|---|---|
| +12V | 12V | CN1/CN2 外部输入 | 隔离电源模块输入 |
| 5V | 5V | 隔离 DC-DC | 隔离侧数字电路 |
| 5VA | 5V | 隔离 DC-DC | 隔离侧模拟电路 |
| 3.3V | 3.3V | XC6206P332MR (U2-1) LDO | MCU 及非隔离侧数字 |
| 3.3VA | 3.3V | 来自 3.3V 经磁珠/滤波 | 非隔离侧模拟电路 |
| 1.65V | 1.65V | TLV431A (U1) + 分压 | ADC 虚拟地/偏置 |
| ISOGND | 0V | 隔离地 | 隔离侧信号参考 |

### 采样电阻
- R16 = 0.1Ω (0805)，连接在 RES_SENSOR+ 和 RES_SENSOR- 之间，用于电流采样

### 连接器

| 连接器 | 类型 | 用途 |
|---|---|---|
| CN1, CN2 | HT396V-3.96-2P (2-pin, 3.96mm) | 电池端子 (+12V / GND) |
| CN3 | xh2_54-4p (4-pin, 2.54mm) | UART 级联输入（从前级来） |
| CN4 | xh2_54-4p (4-pin, 2.54mm) | UART 级联输出（去后级） |
| H5 | B-2100S04P-A110 (4-pin 排针) | SWD 调试接口 |
| H6 | xh2_54-3p (3-pin, 2.54mm) | DS18B20 接口 (DQ, 3.3V, GND) |
| H1~H4 | battery_pin (单针) | 电池测量探针连接点 |

### Uncertainties
- [推断] PA0 (Pin 7) 在网表中连接 ISOGND，但 TSSOP20 的 PA0 应可配置为 GPIO/ADC。需要验证原理图设计意图——可能是为了减少可用 I/O 而接地，或用作 ADC_IN0 但外部接地作参考。
- U8/U9/U10/U11 (SOP-8) 未标注具体型号，根据连接推测为运算放大器（可能是 LMV321 或 LMV358 系列）。
- Pin 2 (PB9/PC14-OSC32_IN) 连接 CN3.1 和 U5.1（隔离器），具体功能在网表中未命名信号，[推断] 可能是某种控制信号或直通连接。
- Pin 3 (PC15-OSC32_OUT) 在网表中未列出，可能悬空或未使用。
- 1.65V 参考电压由 TLV431 产生，供给 ADC 偏置和运放共模电压。

## Build, Flash, And Run Notes

### 构建系统
- **IDE**: Keil MDK-ARM (μVision)
- **编译器**: ArmClang V6.19 (AC6)
- **项目文件**: `battery_re/MDK-ARM/battery_re.uvprojx`
- **设备**: STM32G030F6Px，Pack: Keil.STM32G0xx_DFP.1.4.0
- **CPU**: Cortex-M0+, 12MHz 外部时钟 (HSE 8MHz)
- **编译命令**:
  ```
  C:\Keil_v5\UV4\UV4.exe -j0 -b "MDK-ARM/battery_re.uvprojx" -o "MDK-ARM/build_log.txt"
  ```
  - `-j0`: 抑制状态对话框
  - `-b`: 增量编译；`-r`: 全量重建
- **预定义宏**: `USE_HAL_DRIVER,STM32G030xx`
- **包含路径**: `../Core/Inc;../Drivers/STM32G0xx_HAL_Driver/Inc;../Drivers/STM32G0xx_HAL_Driver/Inc/Legacy;../Drivers/CMSIS/Device/ST/STM32G0xx/Include;../Drivers/CMSIS/Include;..\Drivers\CMSIS\DSP\Include`
- **链接库**: `..\Drivers\CMSIS\DSP\Lib\ARM\arm_cortexM0l_math.lib`

### 已注册源文件（uvprojx 中）
| 分组 | 文件 |
|---|---|
| Application/MDK-ARM | `startup_stm32g030xx.s` |
| Application/User/Core | `main.c`（**需创建**）, `stm32g0xx_it.c`, `stm32g0xx_hal_msp.c`（**需创建**） |
| Drivers/STM32G0xx_HAL_Driver | `stm32g0xx_hal_adc.c`, `hal_adc_ex.c`, `ll_adc.c`, `hal_rcc.c`, `hal_rcc_ex.c`, `ll_rcc.c`, `hal_flash.c`, `hal_flash_ex.c`, `hal_gpio.c`, `hal_dma.c`, `hal_dma_ex.c`, `hal_pwr.c`, `hal_pwr_ex.c`, `hal_cortex.c`, `hal.c`, `hal_exti.c`, `hal_iwdg.c`, `hal_tim.c`, `hal_tim_ex.c`, `hal_uart.c`, `hal_uart_ex.c` |
| Drivers/CMSIS | `system_stm32g0xx.c`, `arm_cortexM0l_math.lib` |

### 已使能 HAL 模块
ADC, TIM, UART, GPIO, EXTI, DMA, RCC, FLASH, PWR, CORTEX, IWDG

### Flash 命令
```
pyocd flash -t stm32g030f6p6 build/firmware.elf
```
（注意：实际项目中 target 需确认为 `stm32g030f6p6` 或 `stm32g030f6`）

### 输出产物
- `battery_re/battery_re.hex`（HEX 格式）
- `battery_re/battery_re.axf`（ELF/Debug 格式）

### 存储器映射
| 区域 | 起始地址 | 大小 |
|---|---|---|
| Flash (IROM) | 0x08000000 | 64 KB (0x10000) |
| SRAM (IRAM) | 0x20000000 | 8 KB (0x2000) |

### 时钟配置（从 system_stm32g0xx.c）
- HSE = 8MHz（外部晶振）
- PLL: M=1, N=16, R=2
- SysClk = (8MHz / 1 * 16) / 2 = **64MHz**
- Flash: 2 wait states (LATENCY_2)
- Flash prefetch buffer 使能

## Constraints And Risks

### 缺失信息
- **main.c** 和 **stm32g0xx_hal_msp.c** 尚不存在（uvprojx 中已引用，需创建）
- U8/U9/U10/U11 运放的具体型号未标出，可能影响模拟电路增益计算
- 自定义 UART 级联协议尚未定义
- 异常数据识别算法的具体实现策略尚未确定
- 相位校正算法和校准方法的细节尚未设计

### 不明确的硬件细节
- PA0 (Pin 7) 接 GND 的意图不明确——是原理图故意接地还是设计约束？
- Pin 2 (PB9) 的具体功能通过无名信号连接到隔离器和连接器，功能待确认
- UART 通信的波特率未在需求中明确指定（[推断] 可能使用 115200 或 9600）
- 内阻测量周期 N 分钟的具体值未确定

### 构建和烧录风险
- Keil 路径硬编码为 `C:\Keil_v5\UV4\UV4.exe`，环境不同可能需调整
- ArmClang V6.19 特定语法：C99 使能，GNU 扩展未使能 (`uGnu=0`)
- 新增源文件需手动注册到 `.uvprojx` 中

### 验收标准不完整
- 无明确的自动化测试脚本
- 无明确的量产测试标准

### 实物验证风险
- 隔离电源和信号路径可能引入噪声，影响 ADC 精度
- 电池充电/放电干扰可能使内阻测量不稳定，需要验证异常数据算法的有效性
- 多电池级联的通信稳定性需在硬件上验证

## Confidence Assessment

| 部分 | 置信度 | 原因 |
|---|---|---|
| Goal | 高 | 用户需求清晰，目标明确 |
| Task Requirements | 高 | 需求文档详细列出所有功能点 |
| Hardware Connection | 中 | 网表提供了完整信号连接，但 MCU pin↔GPIO 映射为推断；部分器件型号未知 |
| Build & Flash | 高 | uvprojx 和现有文件已验证构建配置；需创建 main.c 和 hal_msp.c |
| Constraints & Risks | 中 | 主要风险是有未标注型号的器件和未定义的自定义协议；硬件上 PA0 接地的原因不明 |
```