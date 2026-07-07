# Build Context

## Goal

基于 STM32G030F6P6 微控制器，重构一个电池内阻测量设备的固件。系统使用 PWM 产生 1kHz 方波经电路转换为正弦波注入电池，通过 ADC 同步采集注入电流和电池两端电压并计算内阻，通过 DS18B20 测温，通过 UART1/UART2 级联实现多电池组主从通讯，要求全部使用状态机实现非阻塞逻辑。

## Task Directory

`C:\Users\123\Desktop\neizu\tasknew`

## Source Materials

- `user_req.txt` - 任务需求文档: 功能描述、引脚用途、主从机判断、通讯协议、状态机、编译方式等详细要求 18 条，以及 8 个实施步骤。
- `battery_re/Core/Src/main.c` - 固件入口: HAL 初始化、系统时钟配置 (HSE 8MHz → PLL → 64MHz)、外设句柄定义、空主循环 (shell)。
- `battery_re/Core/Inc/main.h` - 头文件: 引脚宏定义 (ADC、PWM、UART)、外设句柄 extern 声明、函数原型。
- `battery_re/Core/Src/stm32g0xx_hal_msp.c` - HAL MSP 初始化: ADC 引脚 (PA1/PA6/PA7)、PWM 引脚 (PB0 TIM3_CH3)、UART1 (PB6/PB7)、UART2 (PA2/PA3)、DMA1 配置、中断使能。注释中提到 PA5=M_S (主从检测)、PA4=DQ (DS18B20)，但 main.h 未定义对应宏。
- `battery_re/Core/Src/stm32g0xx_it.c` - 中断处理: SysTick、DMA1_Ch1、ADC1、TIM3、TIM14、USART1/2 中断。含弱符号存根 `SCHED_IncTick` 和 `UART_IRQHandler`。
- `battery_re/Core/Src/system_stm32g0xx.c` - 系统初始化: SystemCoreClock = 64MHz、Flash 预取使能、2 个等待周期。
- `battery_re/MDK-ARM/battery_re.uvprojx` - Keil 项目文件: 目标芯片 STM32G030F6Px (TSSOP-20)、Cortex-M0+、IRAM 0x20000000+0x2000、IROM 0x08000000+0x10000、编译器 ARMCLANG V6.19、使用 microlib。
- `battery_re/MDK-ARM/startup_stm32g030xx.s` - 启动文件: 栈 0x400 字节、堆 0x200 字节、完整中断向量表。
- `battery_re/MDK-ARM/battery_re.BAT` - 批处理编译脚本: 调用 ArmClang 和 ArmLink，列出所有编译单元。
- `battery_re/MDK-ARM/battery_re/battery_re.hex` - 已生成的 HEX 固件 (约 5KB Code)。
- `battery_re/MDK-ARM/battery_re/battery_re.map` - 链接映射表。
- `battery_re/MDK-ARM/battery_re_build_gs.log` - 构建日志: 单一错误 `GPIO_AF2_TIM3` 未声明 (已修复)。
- `battery_re/MDK-ARM/battery_re_build_gs2.log` - 成功构建日志: 0 错误、0 警告、Code=6528 RO-data=288 RW-data=12 ZI-data=1580。
- `battery_re/MDK-ARM/build.log` - 后续构建日志: 含 timer_scheduler.c、uart_driver.c 等文件编译 (但未在文件清单中出现这些源文件)。
- `battery_re/MDK-ARM/build_from_codex.log` - 构建日志: 含 adc_sampler.c，Code=14420。
- `battery_re/MDK-ARM/battery_re.uvoptx` - 调试选项: CMSIS-AGDI 调试器、UL2CM3 烧录器、Watch 窗口变量名。
- `battery_re/MDK-ARM/DebugConfig/battery_re_STM32G030F6Px_1.0.0.dbgconf` - 调试配置。
- `battery_re/MDK-ARM/RTE/_battery_re/RTE_Components.h` - 运行时环境组件配置。
- `battery_re/Core/Inc/stm32g0xx_hal_conf.h` - HAL 配置: 启用模块 ADC、IWDG、TIM、UART、GPIO、EXTI、DMA、RCC、FLASH、PWR、CORTEX。
- `Netlist_Schematic1_2026-05-25.tel` - 网表文件 (内容未展开)。
- `battery_re/Drivers/STM32G0xx_HAL_Driver/Inc/stm32g0xx_hal_adc.h` (及其他驱动头文件) - 标准 HAL 驱动。
- `battery_re/Drivers/STM32G0xx_HAL_Driver/Src/stm32g0xx_hal_adc.c` (及其他驱动源文件) - 标准 HAL 实现。
- `hardware_config` (元数据) - 构建/烧录命令配置，但参数匹配 STM32F103，与当前 G030 项目不一致。

## Task Requirements

- **核心功能**: PWM 产生 1kHz/50% 方波 → RC 滤波 → 正弦波 → 恒流注入电池，测量电池两端电压和注入电流计算内阻。定时 1 分钟测一次电压。
- **温度测量**: DS18B20 (DQ 信号线 PA4)，每 30 秒测量一次温度 (额外需求)。
- **主从通讯**: UART2 作为从机接收主机指令；UART1 作为主机向下一个从机发送指令。主机分配从机地址，主机读取所有从机数据 (电压、注入电流、内阻、温度等可扩展数据)。
- **主从识别**: Pin12 (PA5) 上拉输入，开机判断一次：低电平=主机，高电平=从机，判断后改为输入省电。
- **ADC 采样**: 10kHz 采样率采集电池两端交流电压，须与注入电流相位同步。
- **相位校准**: 需对电路导致注入电流与采样电压之间的相位差进行软件校准。
- **多点校准**: 需支持使用实际电阻对注入电流和测量电压进行多点校准。
- **异常数据识别**: 充电/放电逆变器干扰下，需设计异常数据识别算法，确保数据可靠性。
- **状态机**: 整体禁止阻塞，全部使用状态机开发。
- **构建工具**: ARMCLANG V6.19，使用 `C:\Keil_v5\UV4\UV4.exe`，编译命令 `-j0 -b "MDK-ARM/battery_re.uvprojx" -o "MDK-ARM/build_log.txt"`。
- **输出工件**: HEX 文件，输出到 battery_re 工程目录。
- **文档要求**: 需输出整体架构、模块划分、设计方案、通讯协议设计方案。

## Hardware Connection

- **MCU**: STM32G030F6P6 (TSSOP-20，Cortex-M0+，64MHz，64KB Flash，8KB RAM)。 *来源: .uvprojx, main.c*
- **系统时钟**: HSE 8MHz 外部晶振 → PLL (×16, ÷2) → 64MHz SysClk。 *来源: main.c*
- **ADC 输入** (GPIOA，模拟模式，无上下拉):
  - PA1 = ADC1_IN1 (VOLT_ADC - 电池直流电压) *来源: main.h, hal_msp.c*
  - PA6 = ADC1_IN6 (CURRENT_ADC - 注入电流) *来源: main.h, hal_msp.c*
  - PA7 = ADC1_IN7 (RES_ADC - 电池交流电压) *来源: main.h, hal_msp.c*
- **PWM 输出**: PB0 = TIM3_CH3 (AF2)，1kHz 50% 方波。 *来源: main.h, hal_msp.c (注释修正: 应为 AF2)*
- **UART1** (主机，向下游): PB6 = USART1_TX, PB7 = USART1_RX (AF1)。 *来源: main.h, hal_msp.c*
- **UART2** (从机，隔离): PA2 = USART2_TX, PA3 = USART2_RX (AF1)。 *来源: main.h, hal_msp.c*
- **DS18B20**: PA4 = DQ 信号线 (1-wire)。 *来源: hal_msp.c 注释*
- **主从检测** (Pin12): PA5 = M_S，内部上拉，低电平=主机。 *来源: hal_msp.c 注释*
- **ADC DMA**: DMA1_Channel1，圆形模式，半字传输，高优先级。 *来源: hal_msp.c*
- **调试/烧录**: SWD (CMSIS-AGDI, UL2CM3)。 *来源: .uvoptx*
- **采样电阻**: 100mΩ。 *来源: user_req.txt*
- **限定**: PA0 在网络表中接 GND，不可用于 ADC。 *来源: hal_msp.c 注释*

## Build, Flash, And Run Notes

- **项目文件**: `battery_re/MDK-ARM/battery_re.uvprojx`
- **编译器**: ARMCLANG V6.19 (Keil MDK)，使用 Arm Compiler for Embedded。
- **目标 MCU**: STM32G030F6Px
- **构建命令 (源材料)**: `"C:\Keil_v5\UV4\UV4.exe" -j0 -b "MDK-ARM/battery_re.uvprojx" -o "MDK-ARM/build_log.txt"` *来源: user_req.txt*
- **构建命令 (hardware_config 元数据)**: `cmake --build build` — 此命令与 Keil 项目不匹配，**不可用**。
- **闪存命令 (hardware_config 元数据)**: `pyocd flash -t stm32f103c8 build/firmware.elf` — 目标 MCU 是 STM32F103C8，**与当前 G030 项目不匹配，不可用**。
- **闪存方法 (源材料)**: 使用 Keil MDK 通过 UL2CM3 (CMSIS-AGDI) 烧录 STM32G0xx_32.FLM，或使用 pyOCD/OpenOCD 配合 CMSIS-DAP (需配置正确目标)。
- **串口参数 (hardware_config 元数据)**: COM3, 115200 baud — 此为硬件配置元数据，需确认实际端口。
- **主机测试命令 (hardware_config 元数据)**: `python host_tests/smoke_test.py --port COM7 --baud 115200` — 测试脚本路径为 `host_tests/smoke_test.py`，当前目录无此文件。
- **现有工件**: HEX 文件 (`battery_re/MDK-ARM/battery_re/battery_re.hex`)、AXF 文件已成功生成 (0 错误)。
- **成功构建 Code 大小**: 5192 - 14420 字节 (取决于包含的模块)。
- **构建超时**: 120s。*来源: hardware_config*
- **闪存超时**: 120s。*来源: hardware_config*
- **串口超时**: 30s。*来源: hardware_config*
- **主机测试超时**: 120s。*来源: hardware_config*

## Constraints And Risks

- **硬件配置不匹配**: `hardware_config` 元数据中的 `flash_command` 和 `flash_target` 针对 STM32F103C8，与当前 STM32G030F6P6 项目冲突。实际烧录命令需重新指定。
- **DS18B20 和主从检测引脚未在 main.h 中定义**: `hal_msp.c` 注释提到 PA4=DQ, PA5=M_S，但 `main.h` 中无对应宏。此配置未验证。
- **UART 级联协议未定义**: 主从机通讯协议需自定义，当前无任何协议实现或文档。
- **串口端口未确认**: `COM3` 和 `COM7` 可能因硬件连接而异。
- **主机测试脚本缺失**: `host_tests/smoke_test.py` 不在文件清单中，无法执行自动化测试。
- **硬件实物缺失**: 当前只有固件工程，无实际硬件原理图/PCB 文件，硬件连接可靠性无法验证。
- **相位校准和异常数据算法**: 为高级需求，当前无实现代码，需大量数学运算和验证。
- **user_req.txt 提及的 .document-reader 目录**: 未在文件清单中提供，可能包含硬件设计文档缺失。
- **编译错误风险**: 当前项目依赖 `BOARD_PIN_PWM_AF` 宏，之前出现过 `GPIO_AF2_TIM3` 未声明错误 (已在构建日志中记录并修复)。