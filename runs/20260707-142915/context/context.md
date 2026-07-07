好的，作为资深嵌入式固件上下文分析师，我将根据您提供的任务目录和文件内容，生成一份详细的 `context.md` 文档。

# Build Context

## Goal

根据 `user_req.txt` 的要求，重构并实现一个基于 STM32G030F6P6 的电池内阻测量系统固件。任务目标是完成一个包含交流注入、同步采样、温度测量、多机 UART 级联通讯、主从机识别、异常数据处理等功能的非阻塞状态机程序，并确保它能通过 Keil MDK 编译。

## Task Directory

`C:\Users\123\Desktop\neizu\tasknew`

## Source Materials

### `user_req.txt`

- **Type**: requirement doc
- **Summary**: 核心需求文档，详细描述了产品功能、硬件引脚（部分）、通讯协议设计思路、状态机开发要求及编译方式。特别强调需要阅读 `.document-reader` 目录下的网表文件以明确硬件连接。
- **Key facts**:
    - 使用 STM32G030F6P6。
    - 功能：1kHz PWM 产生方波 -> 滤波成正弦波 -> 注入电池 -> 测量电压和电流 -> 计算内阻。定时1分钟测一次电压。
    - 功能：DS18B20 (DQ) 每30秒测温一次。
    - 功能：多电池手拉手 UART 通讯。UART2 作为从机接收主机指令；UART1 作为主机与下一个从机通讯。主机可分配地址，并获取所有从机数据。
    - 主从机判断：Pin12 (PA5) 上拉后，检测外部是否为 0V。若为 0V，则为主机，否则为从机。开机判断一次后改为输入。
    - 采样：10kHz 采集电压，且需与电流相位同步。
    - 校准：支持对电路导致的相位差进行校准；支持使用实际电阻进行多点校准。
    - 异常处理：需要异常数据识别算法，以应对充电/放电干扰。
    - 开发范式：全部使用非阻塞状态机开发。
    - 通讯协议：需自定义 UART 级联协议。
    - 编译工具：`C:\Keil_v5\UV4\UV4.exe`。编译命令：`UV4.exe -j0 -b "MDK-ARM/battery_re.uvprojx" -o "MDK-ARM/build_log.txt"`。
    - 结果文件应直接输出到 `battery_re` 工程目录。
    - **重要提示**：必须阅读 `.document-reader` 目录下的网表文件和 BOM 文件来获取确切的硬件连接。
- **Relevance**: This is the single most important file. The `thinkingmap`, `plan`, `slice`, and `execute_tasks` must be derived directly from the requirements in this file.
- **Confidence**: explicit

### `battery_re\Core\Src\main.c`

- **Type**: source
- **Summary**: 当前项目的入口文件。当前包含一个基础的时钟配置（HSE/PLL 到 64MHz）、HAL 初始化、外设句柄定义和一个空的 `main` 循环。
- **Key facts**:
    - 定义了 `hadc1`, `htim3`, `htim14`, `hdma_adc1`, `huart1`, `huart2` 等句柄.
    - `SystemClock_Config` 配置为 64MHz.
    - 主循环是空的，等待业务逻辑模块填充。
- **Relevance**: This is the compilation entry point and boot file. Future `main()` function should be the top-level state machine dispatcher. The existing clock config and HAL init code should be retained.
- **Confidence**: explicit

### `battery_re\Core\Inc\main.h`

- **Type**: header
- **Summary**: 主头文件，定义了硬件引脚宏和外设句柄的 `extern` 声明。
- **Key facts**:
    - 提供了详细的引脚定义，如 `BOARD_ADC_PIN_VOLT` (PA1), `BOARD_ADC_PIN_CURRENT` (PA6), `BOARD_PIN_PWM_PIN` (PB0), `BOARD_PIN_UART1_TX_PIN` (PB6) 等。这些与 `stm32g0xx_hal_msp.c` 的注释一致。
- **Relevance**: Other modules should `#include "main.h"` to access peripheral handles and pin definitions. The pin definitions here can serve as a reference but must be validated against the netlist.
- **Confidence**: explicit (but needs netlist validation)

### `battery_re\Core\Src\stm32g0xx_hal_msp.c`

- **Type**: source
- **Summary**: HAL 层的 MCU 支持包（MSP）文件，包含 ADC、TIM、UART 等外设的 GPIO 和 DMA 配置。
- **Key facts**:
    - 包含了非常清晰的引脚分配注释。
    - PA1 (VOLT_ADC), PA6 (CURRENT_ADC), PA7 (RES_ADC) 配置为模拟输入。
    - PB0 (TIM3_CH3) 配置为 PWM 输出，AF=GPIO_AF2_TIM3。
    - PA2/PA3 (USART2) 和 PB6/PB7 (USART1) 配置为 UART AF。
    - 初始化了 DMA1_Channel1 用于 ADC，模式为循环模式。
    - 使能了 ADC1 和 DMA1 中断。
- **Relevance**: This file is already correctly configured for the basic peripherals. Future modules should not need to modify the `HAL_XXX_MspInit` functions unless adding new peripherals. The `BOARD_PIN_PWM_AF` was set to `GPIO_AF2_TIM3`; note that a previous build log (`battery_re_build_gs.log`) showed an error because `GPIO_AF2_TIM3` is not defined in `stm32g0xx_hal_gpio.h`. 实际正确的值可能是 `GPIO_AF2_TIM3` or similar.  This needs fixing.
- **Confidence**: explicit (pin names are inferred from comments, validation needed against netlist)

### `battery_re\Core\Src\stm32g0xx_it.c`

- **Type**: source
- **Summary**: 中断服务程序（ISR）文件。
- **Key facts**:
    - 包含 `SysTick_Handler`，调用 `HAL_IncTick()` 和 `SCHED_IncTick()`（一个弱定义存根）。
    - 包含 `UART_IRQHandler()`（一个弱定义存根），用于处理 USART1 和 USART2 中断。它目前只是清空寄存器以防止锁定。
    - 有 `DMA1_Ch1_IRQHandler` 和 `ADC1_IRQHandler`，它们调用相应的 HAL 处理函数。
- **Relevance**: The `UART_IRQHandler` stub is a placeholder for the UART driver module. `SCHED_IncTick` is a placeholder for the scheduler. Future modules will replace these weak definitions.
- **Confidence**: explicit

### `battery_re\MDK-ARM\battery_re.uvprojx`

- **Type**: build config
- **Summary**: Keil MDK 项目文件。定义了芯片型号 (STM32G030F6Px)、编译工具链 (ArmClang V6.19)、Flash/RAM 大小以及包含的源文件。
- **Key facts**:
    - **Device**: STM32G030F6Px
    - **Flash**: 0x08000000, size 0x10000 (64 KB)
    - **RAM**: 0x20000000, size 0x2000 (8 KB)
    - **Compiler**: ARMCC V6.19
    - **Output**: `battery_re\battery_re.axf` and `.hex`
- **Relevance**: This is the build configuration. New source files must be added to this project to be compiled. The compiled object files (.o) and dependency files (.d) in the output directory (`battery_re\battery_re\`) confirm the source files are included.
- **Confidence**: explicit

### `battery_re\MDK-ARM\build_log.txt` (and similar log files)

- **Type**: build config
- **Summary**: 记录了多次编译历史。展示了不同阶段添加的文件（如 `adc_sampler.c`, `timer_scheduler.c`, `uart_driver.c`）和编译结果。
- **Key facts**:
    - 之前的编译尝试包括了 `adc_sampler.c`, `timer_scheduler.c`, `uart_driver.c` 等模块文件。
    - 最后一次成功的编译日志显示 `Program Size: Code=3432 RO-data=288 RW-data=12 ZI-data=1660`，这代表只有基础框架的代码量。
    - `battery_re_build_gs.log` 显示了一个编译错误：`use of undeclared identifier 'GPIO_AF2_TIM3'`。这是一个重要的历史信息，表明在定义 PWM 功能时遇到了问题。
- **Relevance**: The log files show that this project was being developed incrementally. The `GPIO_AF2_TIM3` error is a critical piece of information that the next `execute_tasks` state must fix.
- **Confidence**: explicit

### `Netlist_Schematic1_2026-05-25.tel`

- **Type**: hardware note
- **Summary**: 网表文件。文件名暗示了它包含电路连接的详细信息。
- **Key facts**: 文件内容被截断，无法直接读取。
- **Relevance**: **Crucial**. The `user_req.txt` explicitly demands reading the netlist file. It is the single source of truth for all hardware pin connections. It must be parsed.
- **Confidence**: uncertain (content is truncated/unreadable)

### `hardware_config`

- **Type**: hardware note
- **Summary**: 一个事先提供的硬件配置字典。
- **Key facts**:
    - 包含 `build_command`、`flash_command`、`serial_port`、`host_test_command` 等字段。
    - 需要指出的是，这个 `hardware_config` 可能来自一个通用的模板，其内容（如 `stm32f103c8` 和 `COM7`）与当前实际的 STM32G030F6P6 硬件不符。该配置应被视为起点，但需要根据实际硬件和项目环境进行调整。
- **Relevance**: The `build_command` and `flash_command` can be used as a reference. They are critically important for the CI/CD pipeline.
- **Confidence**: inferred (content may not match actual hardware)

### `battery_re\MDK-ARM\battery_re.sct`

- **Type**: build config
- **Summary**: 链接器分散加载文件。定义了 ROM (0x08000000, 0x10000) 和 RAM (0x20000000, 0x2000) 的布局。
- **Key facts**: RAM 大小为 8KB，这是代码编写时必须牢记的约束。
- **Relevance**: Needed for linker configuration, but likely won't be modified.
- **Confidence**: explicit

## Task Requirements

1.  **核心功能**: 实现交流注入法测量电池内阻。
    - PWM 产生 1kHz, 50% 占空比方波。
    - 通过外部 RC 电路和运放转换为恒流正弦波。
    - 采样电阻 100mΩ。
    - 测量电池两端电压和注入电流，计算内阻。
    - 采样率 10kHz，且必须与电流相位同步。
2.  **电压测量**: 定时 (1 分钟) 测量一次电池电压。
3.  **温度测量**: 使用 DS18B20 (单总线)，每 30 秒测量一次。
4.  **多机通讯**:
    - 使用 UART1 (主机) 和 UART2 (从机) 进行手拉手级联。
    - 协议自定义。
    - 主机可分配地址，并最终获取所有从机的数据 (电压, 电流, 内阻, 温度)。
    - 数据流: 主机读从机1->从机1读从机2->...，然后汇聚回主机。
5.  **主从机识别**:
    - Pin12 (PA5) 上拉输入。开机检测电平。
    - 0V -> 主机，其他 -> 从机。检测后 GPIO 改为输入模式。
6.  **校准**:
    - 相位差校准。
    - 多点电阻校准。
7.  **异常数据处理**:
    - 设计算法识别并排除由充电/放电干扰产生的异常数据。
8.  **开发范式**:
    - 整体程序采用状态机架构，不允许阻塞。
9.  **文档**:
    - 需要输出软件架构、模块划分、模块设计方案、通讯协议设计方案。

## Hardware Connection

- **MCU**: STM32G030F6P6
- **Core**: Cortex-M0+
- **Flash**: 64 KB
- **RAM**: 8 KB
- **ADC Pins**:
    - PA1 (ADC1_IN1): VOLT_ADC (电池电压)
    - PA6 (ADC1_IN6): CURRENT_ADC (注入电流)
    - PA7 (ADC1_IN7): RES_ADC (电池内阻电压)
- **PWM Pin**:
    - PB0 (TIM3_CH3): PWM 输出
- **UART1 (主机，向下游通讯)**:
    - PB6: USART1_TX
    - PB7: USART1_RX
- **UART2 (从机，向上游通讯)**:
    - PA2: USART2_TX
    - PA3: USART2_RX
- **DS18B20**:
    - PA4: DQ 信号线
- **Master/Slave Detect**:
    - PA5: M_S 检测引脚
- **Debug/Flash**: 默认使用 CMSIS-DAP 或 ST-Link。
- **Serial**: 通常使用 UART1 与上位机通信，但具体哪个用作调试日志输出未明确。
- **Note**: `hardware_config` 中指定了 `COM3` 和 `COM7`，但这是旧配置，需要根据实际硬件确定。

## Build, Flash, And Run Notes

- **Build Command** (from `user_req.txt`): `"C:\Keil_v5\UV4\UV4.exe" -j0 -b "MDK-ARM/battery_re.uvprojx" -o "MDK-ARM/build_log.txt"`
    - `hardware_config` 中的 `cmake` 命令已过时，不应使用。
- **Flash Command** (from `hardware_config`, but needs adjustment): `pyocd flash -t stm32f103c8 build/firmware.elf` 是错误的。应为 `pyocd flash -t stm32g030f6p6 <path_to_project>/MDK-ARM/battery_re/battery_re.hex`
- **Flash Tool**: Keil MDK 自带的 Flash 工具或 pyOCD。
- **Serial Observing**:
    - `hardware_config` 指定 `COM3` (项目) 和 `COM7` (测试脚本)，baudrate 115200。
    - 实际的 UART 端口取决于硬件连接。
- **Host Test Command** (from `hardware_config`): `python host_tests/smoke_test.py --port COM7 --baud 115200`
    - 该文件不存在，需要创建。
- **Working Directory**: `C:\Users\123\Desktop\neizu\tasknew`
- **Output Artifacts**: `MDK-ARM/battery_re/battery_re.axf`, `.hex`, `.map`
- **Required Tools**: Keil MDK v5 (with ArmClang V6.19), (optional) pyOCD, Python (for host test).

## Existing Code Overview

- **Entry Point**: `Core/Src/main.c`
- **User Code**:
    - `Core/Src/main.c`: 时钟配置和空的主循环。
    - `Core/Src/stm32g0xx_it.c`: 中断处理函数，包含 `SCHED_IncTick` 和 `UART_IRQHandler` 的弱定义存根。
    - `Core/Src/stm32g0xx_hal_msp.c`: MSP 初始化，已完成大部分外设的底层配置。
    - `Core/Inc/main.h`: 宏定义和全局句柄声明。
- **Generated/Vendor Code**:
    - `Drivers/STM32G0xx_HAL_Driver/`: STM32G0 HAL 驱动库。
    - `Drivers/CMSIS/`: CMSIS 核心库。
    - `MDK-ARM/startup_stm32g030xx.s`: 启动文件。
    - `Core/Src/system_stm32g0xx.c`: 系统初始化文件。
- **Key Modification Points**:
    1.  **`main.c`**: 实现顶层状态机调度循环。
    2.  **`Core/Src/`**: 需创建 `timer_scheduler.c`, `uart_driver.c`, `ds18b20.c`, `adc_sampler.c`, `comm_protocol.c`, `resistance_calc.c` 等业务模块文件。
    3.  **`Core/Inc/`**: 需创建对应的头文件。
    4.  **`battery_re.uvprojx`**: 必须手动将新创建的 `.c` 和 `.h` 文件添加到项目中。
- **Pre-existing Modules (from build logs)**: 之前的开发尝试创建过 `adc_sampler.c`, `timer_scheduler.c`, `uart_driver.c` 等，但当前文件清单中没有它们。这意味着项目框架已被清理，需要从零开始或基于上次成功编译的快照进行开发。

## Constraints And Risks

1.  **Missing Hardware Details**: `user_req.txt` 明确要求阅读 `.document-reader` 目录下的网表文件和 BOM 文件。这些文件（如 `.tel` 文件内容被截断，且没有 `.bom` 文件）的详细信息至关重要，但它们不在当前的 `file_manifest` 中，其内容会直接影响 `stm32g0xx_hal_msp.c` 中的引脚配置和参数。这是最大的风险。
2.  **`GPIO_AF2_TIM3` Error**: 根据 `battery_re_build_gs.log`，`BOARD_PIN_PWM_AF` 的定义有误。在 `stm32g0xx_hal_gpio.h` 中可能不存在 `GPIO_AF2_TIM3`，需要查找正确的宏定义或用数字 `2` 代替。这是一个必须立刻修复的已知编译错误。
3.  **UART Protocol**: 多机通讯协议需要从零开始设计。`user_req.txt` 仅提供指导性描述（自定义协议，主机分配地址等），没有具体字节定义。
4.  **Interrupt Priorities**: 所有中断优先级在 `stm32g0xx_hal_msp.c` 中都被设置为 `0`（最高）。在实际多任务运行中，可能需要根据实时性要求调整优先级，以防止冲突。
5.  **Real-time Sampling**: 10kHz 采样且需要相位同步。在 64MHz 的 M0+上必须仔细设计 DMA 和定时器触发机制，以确保不丢失数据且 CPU 有足够余量处理其他任务。
6.  **State Machine Complexity**: 整个系统使用状态机开发，增加了软件设计和调试的复杂度。所有模块的内部状态以及模块间的通信机制需要清晰定义。
7.  **Unknown Host Test**: `host_test_command` 指向的脚本 `smoke_test.py` 不存在。这需要后续创建。

## Next-State Guidance

For the immediate next state (`thinkingmap` and `plan`):

1.  **Read Netlist First**: **The absolute highest priority** is to locate and parse the `.document-reader` files (especially the netlist). If they cannot be found, the `plan` must state the risk and make reasonable assumptions for the initial design, but mark them as `[INFERRED]`.
2.  **Fix Compilation Error**: Immediately plan to fix the `BOARD_PIN_PWM_AF` macro in `main.h` or `stm32g0xx_hal_msp.c`. Change it to `GPIO_AF1_TIM3` or `GPIO_AF2_TIM3` depending on what's correct for the used microcontroller.
3.  **Architect the System**: The `thinkingmap` must outline the high-level modules (Scheduler, ADC Sampler, UART Driver, Comm Protocol, Resistance Measurement, Temperature Sensor). The `plan` must detail the state machine for each module.
4.  **Define Communication Protocol**: Before writing the `comm_protocol` module, a formal protocol must be designed and documented (e.g., start byte, length, command, data, checksum).
5.  **Create Source Files**: The `slice` and `execute_tasks` must create the new `.c` and `.h` modules in the `Core/Src` and `Core/Inc` directories and **ensure they are added to the Keil project**.
6.  **Use Correct Build Command**: The `execute_tasks` state must use the command from `user_req.txt`: `"C:\Keil_v5\UV4\UV4.exe" -j0 -b "MDK-ARM/battery_re.uvprojx" -o "MDK-ARM/build_log.txt"`. Do not use `cmake`.
7.  **Do Not Touch**: Don't modify `system_stm32g0xx.c`, `startup_stm32g030xx.s`, or the HAL library source files. Only the user code in `Core/` and the project file (`uvprojx`) should be changed/added.

## Evidence Index

- **Fact**: Main task is to implement a battery internal resistance measurement system using STM32G030F6P6.
  Source: `user_req.txt`
  Confidence: explicit
- **Fact**: Hardware pin mapping (PA1, PA6, PA7 for ADC; PB0 for PWM; PB6/PB7 for UART1; PA2/PA3 for UART2; PA4 for DS18B20; PA5 for master/slave detect).
  Source: `stm32g0xx_hal_msp.c` comments
  Confidence: inferred (requires netlist validation)
- **Fact**: System clock is configured for 64 MHz via HSE PLL.
  Source: `main.c`
  Confidence: explicit
- **Fact**: Build tool is Keil MDK v5, command is `"C:\Keil_v5\UV4\UV4.exe" -j0 -b "MDK-ARM/battery_re.uvprojx" -o "MDK-ARM/build_log.txt"`.
  Source: `user_req.txt`
  Confidence: explicit
- **Fact**: A previous compilation attempt failed due to an undefined identifier `GPIO_AF2_TIM3`.
  Source: `battery_re_build_gs.log`
  Confidence: explicit
- **Fact**: There is an instruction to read `.document-reader` directory files for hardware details, but these files are not included in the provided manifest.
  Source: `user_req.txt`
  Confidence: explicit
- **Fact**: Hardware config provides `pyocd flash` and serial port commands, but these may be based on a different hardware setup (e.g., stm32f103c8).
  Source: `hardware_config`
  Confidence: uncertain