# Build Context

## Goal

根据用户需求文档 `user_req.txt` 以及提供的工程框架，在 STM32G030F6P6 平台上实现一个电池内阻测量系统。系统功能包括：使用 PWM 产生 1kHz 50% 占空比的方波，经 RC 滤波形成正弦波注入电池，测量电池两端电压和注入电流以计算内阻；每 1 分钟定时测量一次电压；通过 DS18B20 每 30 秒测量一次温度；支持多个电池单元手拉手 UART 级联通信（主机分配从机地址，主机轮询获取所有从机的电压、电流、内阻、温度等数据）；通过 GPIO pin12 上拉输入判断本机是主机（0V）还是从机；采集注入电流产生的电压时需 10kHz 同步采样；需进行相位校准和真实电阻多点校准；整体采用非阻塞状态机架构，包含异常数据识别算法。要求输出完整的软件架构设计、模块划分、设计方案、代码实现、通信协议设计，并使用 Keil MDK 实现编译通过，最终输出设计文档和可编译项目。

## Task Directory

`C:\Users\123\Desktop\neizu\tasknew`

## Source Materials

### Directory Index

- `battery_re/` – 项目根目录，包含 Core、Drivers、MDK-ARM 等子目录
- `battery_re/Core/` – 应用代码目录，含 Inc 和 Src
- `battery_re/Core/Inc/` – 用户生成的头文件（main.h、stm32g0xx_it.h、stm32g0xx_hal_conf.h）
- `battery_re/Core/Src/` – 用户生成的源文件（main.c、stm32g0xx_it.c、system_stm32g0xx.c）
- `battery_re/Drivers/` – 供应商驱动库根目录
- `battery_re/Drivers/CMSIS/` – CMSIS 核心/支持文件，包括 Core、DSP、NN 等子目录；背景依赖，非主任务逻辑
- `battery_re/Drivers/STM32G0xx_HAL_Driver/` – STM32G0 HAL 驱动源码和头文件；背景依赖
- `battery_re/MDK-ARM/` – Keil MDK 工程文件、编译日志、输出产物
- `battery_re/MDK-ARM/battery_re/` – 编译目标文件夹，包含 .axf、.hex、.map、.htm、.lnp、.sct 等
- `battery_re/MDK-ARM/DebugConfig/` – 调试配置（含两个芯片的 .dbgconf）
- `battery_re/MDK-ARM/RTE/` – Run-Time Environment 文件（RTE_Components.h）

### Important File Index

- `user_req.txt` – 任务需求文档：描述了完整功能、引脚要求、通信协议、编译要求等（内容截断）
- `battery_re\MDK-ARM\battery_re.uvprojx` – Keil 工程文件：目标芯片 STM32G030F6Px，编译器 ArmClang V6.19，输出目录 battery_re\，生成 hex 文件
- `battery_re\MDK-ARM\battery_re.uvoptx` – 工程选项文件：调试器配置、看窗变量等
- `battery_re\MDK-ARM\battery_re.BAT` – 构建批处理：使用 ArmClang 编译各源文件并链接、生成 hex
- `battery_re\Core\Src\stm32g0xx_it.c` – 中断服务例程：包含 SysTick、DMA、ADC、TIM、UART 中断处理，引用外部 handle 和弱符号 SCHED_IncTick / UART_IRQHandler
- `battery_re\Core\Src\system_stm32g0xx.c` – 系统初始化：配置 Flash 预取、设置 64MHz 系统时钟（HSE 8MHz -> PLL -> 64MHz）
- `battery_re\Core\Inc\stm32g0xx_hal_conf.h` – HAL 模块配置：使能 ADC、TIM、UART、IWDG、DMA、GPIO、EXTI、RCC、FLASH、PWR、CORTEX 等模块
- `battery_re\Core\Inc\stm32g0xx_it.h` – 中断声明：额外声明 DMA1_Ch1、ADC1、TIM1_BRK、TIM3、TIM14、USART1、USART2 中断
- `battery_re\MDK-ARM\startup_stm32g030xx.s` – 启动文件：中断向量表、堆栈配置、Reset_Handler 调用 SystemInit 和 __main
- `Netlist_Schematic1_2026-05-25.tel` – 网表文件（.tel）：包含电路连接信息（未直接解析，应包含 MCU 引脚与外设的映射）
- `battery_re\MDK-ARM\battery_re\battery_re.map` – 链接映射文件：显示各符号引用、section 分布、栈使用估算等
- `battery_re\MDK-ARM\battery_re\battery_re.axf` – 可执行文件（已编译成功，代码 5192 字节，0 错误 0 警告）
- `battery_re\MDK-ARM\battery_re\battery_re.hex` – Intel HEX 格式固件（可用于烧录）
- 多个编译日志（如 build.log、build_log.txt、fresh_build.log 等）显示以往构建成功或失败记录，GPIO_AF2_TIM3 未声明错误已在后续日志中修复

## Task Requirements

| 需求项 | 描述 |
|--------|------|
| 交流激励源 | PWM 产生 1kHz 50% 方波，经 RC 滤波形成正弦波注入电池 |
| 内阻测量 | 测量电池两端电压与注入电流，计算内阻（采样电阻 100mΩ） |
| 电压定时测量 | 每 1 分钟测量一次电池电压 |
| 温度测量 | DS18B20 单总线测温，每 30 秒一次 |
| UART 级联通信 | UART2 作为从机接收上级主机指令；UART1 作为主机发送指令给下一级从机；主机可分配地址、读取所有从机数据（电压、注入电流、内阻、温度等） |
| 主从识别 | 上电时读 pin12（内部上拉）：0V 为主机，否则为从机；之后改为输入模式省电 |
| 同步采样 | 注入电流产生的电压采集需 10kHz 采样率，并与电流相位同步 |
| 相位校准 | 对电路引起的注入电流与采样电压之间的相位差进行校准 |
| 多点校准 | 使用实际电阻对注入电流测得的电压与真实电阻进行多点校准 |
| 状态机架构 | 整体采用非阻塞状态机，禁止阻塞等待 |
| 异常数据识别 | 算法识别充电/放电干扰导致的异常数据并丢弃 |
| 协议自定义 | 自定义 UART 级联通信协议（需输出设计方案） |
| 编译工具 | 使用 Keil MDK（C:\Keil_v5\UV4\UV4.exe），编译器 ArmClang V6.19，工程文件 battery_re.uvprojx |
| 编译参数 | 必须使用 `-j0` 抑制对话框，`-b` 增量编译或 `-r` 全量重建，日志输出到文件；退出码 0 成功，1 警告通过，2-20 错误 |
| 输出位置 | 代码直接输出到已有 battery_re 工程中，不破坏现有结构 |
| 文档 | 需输出软件整体架构、模块划分、设计方案、通信协议设计，与代码同等重要 |

**缺失信息**：无显式测试脚本、单元测试要求；验收标准未明确定义（如内阻精度、通信成功率）。

## Hardware Connection

| 项 | 值 | 来源 |
|----|-----|----|
| MCU | STM32G030F6P6 (TSSOP-20) | user_req.txt、uvprojx |
| 主从判断引脚 | Pin12（内部上拉输入，0V=主机，否则从机） | user_req.txt |
| DS18B20 | DQ 信号线（具体引脚未指定，需从网表或 BOM 确认） | user_req.txt |
| UART1 | 作为主机与下一级从机通讯（具体引脚见硬件连接） | user_req.txt |
| UART2 | 作为从机接收上级主机指令（具体引脚见硬件连接） | user_req.txt |
| PWM 输出 | 产生 1kHz 方波，经 RC 滤波（具体引脚未指定） | user_req.txt |
| ADC 采样 | 采集电池电压和采样电阻电压（具体通道未指定） | user_req.txt |
| 采样电阻 | 100 mΩ | user_req.txt |
| 晶振 | HSE 8MHz（system_stm32g0xx.c 使用） | 代码推断 |
| 调试接口 | SWD（uvoptx 配置了 UL2CM3 和 CMSIS_AGDI） | uvoptx |
| 串口调试 | 未明确指定，硬件配置预设 COM3/115200（需验证） | hardware_config |
| 网表文件 | `Netlist_Schematic1_2026-05-25.tel` 包含详细电路连接 | 文件存在 |
| BOM 与 MCU 说明书 | 在 `.document-reader` 中，未直接提供（需自行读取） | user_req.txt |

**注意**：除 pin12 外，其他外设（DS18B20、UART1/2、PWM、ADC 通道）的具体引脚号未在 user_req.txt 中给出，需通过网表文件和 BOM 确认。

## Build, Flash, And Run Notes

- **构建命令（来自 user_req.txt）**：
  ```
  "C:\Keil_v5\UV4\UV4.exe" -j0 -b "MDK-ARM/battery_re.uvprojx" -o "MDK-ARM/build_log.txt"
  ```
  也可使用 `-r` 全量重建。编译成功退出码 0，警告但无错误退出码 1，错误退出码 2-20。

- **构建工具链**：Keil MDK 5.38，ArmClang V6.19，已生成 .axf 和 .hex 文件。

- **烧录命令（来自 hardware_config，需验证）**：
  ```
  pyocd flash -t stm32f103c8 build/firmware.elf
  ```
  **注意**：此命令的 -t 参数为 stm32f103c8，与目标芯片 STM32G030F6P6 不符，实际烧录应使用 `-t stm32g030f6` 或通过 Keil 的 UL2CM3 下载。建议使用 Keil 内置下载或修正 pyOCD 命令。

- **串口观察（来自 hardware_config）**：COM3，波特率 115200，超时 30s。但 user_req.txt 未明确指定调试串口，仅提到 UART1/2 用于级联通信。

- **主机测试命令（来自 hardware_config）**：
  ```
  python host_tests/smoke_test.py --port COM7 --baud 115200
  ```
  可能用于验证级联通信，但 `host_tests/` 目录不存在于任务目录中。

- **输出产物**：`battery_re/MDK-ARM/battery_re/battery_re.hex` 可作为烧录文件。

- **工作目录**：`C:\Users\123\Desktop\neizu\tasknew`（即 task_directory）。

## Constraints And Risks

1. **需求文档不完整**：`user_req.txt` 内容被截断，可能遗漏部分需求或约束。
2. **硬件连接细节缺失**：除 pin12 外，DS18B20、UART1/2 TX/RX、PWM 输出引脚、ADC 输入通道均未明确指定，必须从网表文件 `Netlist_Schematic1_2026-05-25.tel` 和 `.document-reader` 中提取，但这些文件未直接解析（需单独读取）。
3. **网表与 BOM 依赖**：`Netlist_Schematic1_2026-05-25.tel` 是原始格式，可能需要解析或转换为可读标记；`.document-reader` 是否存在及内容未知（user_req.txt 提到但未提供）。
4. **烧录命令不一致**：`hardware_config` 中的 pyOCD 命令目标芯片为 `stm32f103c8`，与工程 STM32G030F6P6 不符，可能无法直接使用。实际烧录应使用 Keil 的 UL2CM3 或更正 pyOCD 命令。
5. **串口配置不确定**：调试串口号（COM3 vs COM7）和波特率 115200 来自硬件配置预设，未在 user_req.txt 中确认，可能需根据实际硬件调整。
6. **主机测试脚本缺失**：`host_tests/smoke_test.py` 不存在于任务目录中，测试命令可能无法执行。
7. **电源与外部模块干扰**：user_req.txt 提到充电/放电干扰需处理，但未提供具体干扰特征，异常数据识别算法需要自行设计。
8. **原工程文件被删除**：`user_req.txt` 明确说原文件已被删除，需要完全重构代码，仅保留基础框架文件和 HAL 库。现有 `main.c` 和 `stm32g0xx_it.c` 可能只是模板或旧代码，需重新实现。
9. **启动文件未定义 `GPIO_AF2_TIM3`**：早期编译日志显示该宏未定义，后修复。需确保当前工程中正确包含所有必要的宏定义。
10. **资源限制**：STM32G030F6P6 仅有 32KB Flash、8KB RAM，需留意代码体积和堆栈使用（当前编译后 Code=5192 bytes，ZI-data=1580 bytes，剩余空间较多）。
11. **非阻塞状态机要求**：所有模块需设计为事件驱动或定时轮询，不可使用延时循环。
12. **12 位 ADC 与 10kHz 同步采样**：需配置定时器触发 ADC 以同步 PWM 相位，并处理 DMA 传输。