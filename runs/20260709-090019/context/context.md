Now I have enough information. Let me write the context.md.

```markdown
# Build Context

## Goal

完成电池内阻测量系统的固件开发。基于 STM32G030F6P6 (TSSOP-20) MCU，实现：

- 产生 1kHz 50% 占空比方波经 RC 滤波 → 正弦波 → 恒流向电池注入交流电流
- 测量电池两端电压、注入电流，计算电池内阻
- 每 1 分钟测量一次
- DS18B20 温度测量（DQ 引脚），每 30 秒一次
- UART2 作为从机接收上级主机指令
- UART1 作为主机与下级从机通讯，支持地址分配、数据轮询
- M/S 引脚（上拉判断）区分主/从机：高电平=主机，低电平=从机
- 10kHz ADC 采集，与电流相位同步
- 相位差校正、多点电阻校准
- 异常数据识别算法（抗充放电干扰）
- 整体基于状态机，禁止阻塞
- 输出到 Keil MDK-ARM 工程，通过编译

## Source Materials

### Directory Overview

| 目录 | 说明 |
|------|------|
| `battery_re/Core/` | 应用核心代码：Inc (头文件), Src (源文件) |
| `battery_re/Drivers/STM32G0xx_HAL_Driver/` | STM32G0xx HAL 驱动库 |
| `battery_re/Drivers/CMSIS/` | CMSIS 核心、DSP 库、NN 库（仅 DSP lib 被引用） |
| `battery_re/MDK-ARM/` | Keil 工程文件、编译输出、启动文件 |
| `.document-reader/` | 文档阅读器输出：DS12991 数据手册、BOM、网表 |
| `.understand-anything/` | 项目理解辅助文件（未使用） |

### Key Files Inspected

- `user_req.txt` — 用户需求文档，描述全部功能、引脚、协议、约束
- `Netlist_Schematic1_2026-05-25.tel` — 电路网表，列出所有网络连接
- `.document-reader/BOM/document.md` — BOM 表，列出全部元器件
- `.document-reader/BOM_Board1_Schematic1_2026-05-23/document.md` — 另一份 BOM（含器件厂商/型号）
- `.document-reader/DS12991/document.md` — STM32G030x6/x8 数据手册（5191 行）
- `.document-reader/netlist/document.md` — 网表文档副本
- `battery_re/Core/Inc/stm32g0xx_hal_conf.h` — HAL 模块选择：ADC、TIM、UART、IWDG、DMA、GPIO、EXTI、RCC、FLASH、PWR、CORTEX
- `battery_re/Core/Src/system_stm32g0xx.c` — 系统时钟配置：HSE 8MHz → PLL → 64MHz SysClk
- `battery_re/Core/Src/stm32g0xx_it.c` — 中断服务函数（含弱符号桩：SCHED_IncTick、UART_IRQHandler）
- `battery_re/Core/Inc/stm32g0xx_it.h` — 中断声明
- `battery_re/MDK-ARM/startup_stm32g030xx.s` — 启动文件，Stack=0x400, Heap=0x200
- `battery_re/MDK-ARM/battery_re.uvprojx` — Keil 工程配置
- `battery_re/MDK-ARM/battery_re.sct` — 链接脚本：FLASH 0x08000000 (64KB), RAM 0x20000000 (8KB)
- `battery_re/MDK-ARM/build_log.txt` — 最近一次编译日志（0 Error, 0 Warning）
- `__ds12991_tmp.txt` / `__out1.txt` — 数据手册/特征摘要副本

## Task Requirements

### 功能行为
- 产生 1kHz PWM（TIM3_CH3, 50% duty）→ RC 滤波 → 正弦波 → 运放恒流 → 注入电池
- 测量电池两端电压（VOLT_ADC）和注入电流（CURRENT_ADC），计算内阻
- 使用采样电阻 R16=0.1Ω 作为电流采样
- 每 1 分钟测量一次内阻
- DS18B20 温度测量（DQ, PA4），每 30 秒一次
- 10kHz ADC 采集，必须与电流相位同步
- 相位差校正算法
- 多点电阻校准（使用实际电阻）
- 异常数据识别（排除充放电干扰）

### 接口与协议
- UART1（PB6/PB7, 主机）：与下级从机通讯，发送指令，分配地址，轮询数据
- UART2（PA2/PA3, 从机）：接收上级主机指令
- 自定义级联通讯协议
- 主机可给从机分配地址，读取所有从机电压/电流/内阻/温度等数据
- 主机从 1 开始编号，1 号为主机，其余为从机

### 输入/输出与指示
- M_S 引脚（PA5）：上拉输入，开机判断主/从（高=主机，低=从机），判断后改为输入模式省电
- DQ（PA4）：DS18B20 单总线

### 时序与性能
- 全部基于状态机，禁止阻塞
- SysTick = 1ms（HAL 时钟基准）
- 1kHz PWM 输出
- 10kHz ADC 同步采集
- 1 分钟周期测量内阻
- 30 秒周期测量温度

### 测试与验收标准
- 通过 Keil 编译（0 Error, 0 Warning）
- 编译命令：`UV4.exe -j0 -b "MDK-ARM/battery_re.uvprojx" -o "MDK-ARM/build_log.txt"`
- 输出固件：`battery_re.hex`、`battery_re.axf`

## Hardware Connection

### MCU / SoC
- 型号：STM32G030F6P6TR (STMicroelectronics)
- 核心：ARM Cortex-M0+, 64 MHz
- Flash：64 KB, SRAM：8 KB
- 封装：TSSOP-20 (6.5×4.4mm, 0.65mm pitch)
- 标识：U3-1（原理图位号）

### Debug / Flash 接口
- 协议：Serial Wire Debug (SWD)
- 连接器：H5（4-pin 排针, B-2100S04P-A110）

| H5 引脚 | 信号 | MCU 引脚 |
|---------|------|----------|
| 1 | 3.3V | VDD |
| 2 | ISOGND | GND |
| 3 | SWDIO | PA13 (Pin 18) |
| 4 | SWCLK | PA14 (Pin 19) |

### 外设接线

| 信号 | MCU 引脚 | TSSOP-20 Pin | GPIO | 目标器件 | 方向 | 说明 |
|------|----------|-------------|------|---------|------|------|
| UART1_RX | PB7 | 1 | USART1_RX (AF0) | CN3.1→U5(隔离器)→外部 | 输入 | 接收下级从机数据 |
| UART1_TX | PB6 | 20 | USART1_TX (AF0) | CN3.2→U5(隔离器)→外部 | 输出 | 发送指令给下级从机 |
| UART2_RX | PA3 | 10 | USART2_RX (AF1) | CN4.2→R11(10Ω)→外部 | 输入 | 接收上级主机指令 |
| UART2_TX | PA2 | 9 | USART2_TX (AF1) | CN4.3→R10(10Ω)→外部 | 输出 | 发送数据给上级主机 |
| DQ | PA4 | 11 | GPIO | H6.2→R6(4.7kΩ 上拉)→DS18B20 | I/O | 单总线温度传感器 |
| M_S | PA5 | 12 | GPIO/输入 | R9(100kΩ 上拉至 3.3V) | 输入 | 主/从机判断，开机检测 |
| TIM3_CH3 | PB0 | 15 | TIM3_CH3 (AF1) | R21(100kΩ)→RC滤波→OP1 | 输出 | 1kHz PWM 产生正弦波 |
| VOLT_ADC | PA1 | 8 | ADC1_IN1 | R4-1/R5-1 分压网络 | 输入 | 电池电压采样 |
| CURRENT_ADC | PA6 | 13 | ADC1_IN6 | R52(100kΩ)→U11→电流检测 | 输入 | 注入电流采样(R16=0.1Ω) |
| RES_ADC | PA7 | 14 | ADC1_IN7 | R38(10kΩ)→U10→电池端电压 | 输入 | 内阻测量电压 |
| NRST | NRST | 6 | - | U6(RC复位) | 输入 | 外部复位 |
| VDD/VDDA | VDD | 4 | - | 3.3V供电 | 电源 | |
| VSS/VSSA | VSS | 5 | - | ISOGND | 电源 | |

### 连接器定义

| 连接器 | 类型 | 引脚 | 信号 |
|--------|------|------|------|
| CN1, CN2 | 2P-3.96mm | 1=+12V, 2=GND | 电池/电源接口 |
| CN3 | 4P-XH2.54 | 1=UART1_RX, 2=UART1_TX, 3=UART1_CTS?, 4=UART1_RTS? | 级联(主)→下级 |
| CN4 | 4P-XH2.54 | 1=3.3V, 2=UART2_RX, 3=UART2_TX, 4=ISOGND | 级联(从)←上级 |
| H5 | 4P-2.54mm | 1=3.3V, 2=GND, 3=SWDIO, 4=SWCLK | SWD 调试 |
| H6 | 3P-XH2.54 | 1=3.3V, 2=DQ, 3=GND | DS18B20 |
| H1~H4 | 1P | 电池测试点 | 电池正/负检测 |

### 电源

| 网络 | 电压 | 来源 | 说明 |
|------|------|------|------|
| +12V | 12V | CN1/CN2 输入 | 主电源 |
| 5V | 5V | U1-1 (VPS8701B) 隔离 Flyback | 隔离侧供电 |
| 5VA | 5V | L1→OP1 | 运放供电 |
| 3.3V | 3.3V | U2-1 (XC6206P332MR) LDO | MCU 及数字电路 |
| 3.3VA | 3.3V | R1(10Ω)→3.3V | 模拟供电滤波 |
| 1.65V | 1.65V | U1 (TLV431A) 分流基准 | ADC 参考/偏置 |

### [推断] 电路模块

基于网表和 BOM 推断的关键电路模块：

1. **隔离 Flyback 变换器**：U1-1(VPS8701B) + T1-1(VPT87DFB01B 变压器) + D2-1/D3-1(RB160M-30 整流) → 产生隔离 5V
2. **1.65V 基准**：U1(TLV431A) + R3(660Ω) + R4(820Ω) → 分压设置 1.65V 参考
3. **数字隔离**：U5(CA-IS3721LS) → 隔离 UART1 信号
4. **恒流源**：OP1(LM258 双运放) → 将 PWM→正弦波转换为交流恒流
5. **信号调理**：U8/U9/U10/U11(SOP-8) → 滤波、放大、I/V 转换
6. **RC 滤波器**：R21(100k) + C7(1nF)，R20(100k) + C6(1nF) 等多级 → PWM 转正弦波
7. **隔离电源**：R4(820) + R5(2.49k) → 反馈分压

**注意**：网表中 MCU 引脚 U3-1.7 连接到 ISOGND，这符合 TSSOP-20 的 VSS 引脚。

## Build, Flash, And Run Notes

- **构建系统**：Keil MDK-ARM v5 (ARMCLANG V6.19)
- **工程文件**：`battery_re/MDK-ARM/battery_re.uvprojx`
- **编译命令**：`C:\Keil_v5\UV4\UV4.exe -j0 -b "MDK-ARM/battery_re.uvprojx" -o "MDK-ARM/build_log.txt"`
- **全局宏定义**：`USE_HAL_DRIVER, STM32G030xx`
- **包含路径**：`../Core/Inc; ../Drivers/STM32G0xx_HAL_Driver/Inc; ../Drivers/STM32G0xx_HAL_Driver/Inc/Legacy; ../Drivers/CMSIS/Device/ST/STM32G0xx/Include; ../Drivers/CMSIS/Include; ..\Drivers\CMSIS\DSP\Include`
- **链接脚本**：IROM=0x08000000(64KB), IRAM=0x20000000(8KB)
- **输出文件**：`battery_re/MDK-ARM/battery_re/battery_re.axf` + `battery_re.hex`
- **Flash 命令**：`pyocd flash -t stm32f103c8 build/firmware.elf`（注意：此命令与目标 MCU STM32G030F6P6 不符，需调整为目标 `stm32g030f6` 或使用 ST-Link Utility）
- **串口**：COM3, 115200 baud（默认调试串口）
- **主机测试**：`python host_tests/smoke_test.py --port COM7 --baud 115200`

### 已配置的 HAL 模块
ADC、TIM、UART、IWDG、DMA、GPIO、EXTI、RCC、FLASH、PWR、CORTEX

### 已存在的源文件结构

| 组名 | 文件 |
|------|------|
| Application/MDK-ARM | startup_stm32g030xx.s |
| Application/User/Core | main.c (需创建), stm32g0xx_it.c, stm32g0xx_hal_msp.c (需创建) |
| Drivers/STM32G0xx_HAL_Driver | hal, hal_adc, hal_adc_ex, ll_adc, hal_rcc, hal_rcc_ex, ll_rcc, hal_flash, hal_flash_ex, hal_gpio, hal_dma, hal_dma_ex, hal_pwr, hal_pwr_ex, hal_cortex, hal_exti, hal_iwdg, hal_tim, hal_tim_ex, hal_uart, hal_uart_ex |
| Drivers/CMSIS | system_stm32g0xx.c, arm_cortexM0l_math.lib |

## 已知的中断桩
- `SCHED_IncTick(void)` — 弱符号，被 SysTick_Handler 调用
- `UART_IRQHandler(uint32_t id)` — 弱符号，被 USART1/2_IRQHandler 调用

## Constraints And Risks

### 缺失文件（需创建）
- `Core/Src/main.c` — 主程序（被编译但不存在）
- `Core/Src/stm32g0xx_hal_msp.c` — HAL MSP 初始化（被编译但不存在）

### 不确定的硬件细节
- UART 隔离器 CA-IS3721LS 的具体连接方式（网表显示 CN3.1→U5.1, CN3.2→U5.2, CN3.4→U5.4, CN3.3→U5.3 连接 UART1 信号及流控）
- U8/U9/U10/U11 的具体型号和功能（SOP-8 封装，未标注型号）
- R16(0.1Ω) 标注为"需要采购"，可能不存在于实物
- 相位同步具体实现方式需进一步设计
- 异常数据识别算法需自定义设计

### 编译/烧录风险
- 提供的 flash 命令 `pyocd flash -t stm32f103c8` 指定的是 STM32F103C8，与目标 STM32G030F6P6 不符，需修正
- Keil 路径 `C:\Keil_v5\UV4\UV4.exe` 需确认存在
- DSP 库 `arm_cortexM0l_math.lib` 已被引用到工程中

### 通讯协议
- 自定义级联协议需完全自主设计
- 主机扫描从机、地址分配、数据轮询流程待定

### 验收标准
- 编译无错误/警告
- 功能完整实现并通过逻辑验证
- 文档（架构、模块设计、通讯协议）与代码同等重要

## Confidence Assessment

| 章节 | 置信度 | 原因 |
|------|--------|------|
| Goal | 高 | 用户需求文档明确 |
| Task Requirements | 高 | 19 条需求详细列出 |
| Hardware Connection | 中 | 网表清晰，但 U8-U11 型号未知，部分模块功能为推断 |
| Build & Flash | 中 | 工程配置已知，但 flash 命令与目标 MCU 不匹配 |
| Constraints & Risks | 高 | 缺失文件、不确定器件、协议需自定义均有记录 |
```