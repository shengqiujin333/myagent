Now I have all the information needed. Let me write the comprehensive `context.md`.

```markdown
# Build Context

## Goal

基于 STM32G030F6P6 (TSSOP-20) MCU，重构电池内阻测量系统的完整固件。系统通过 PWM 产生 1kHz 方波，经 RC 滤波器形成正弦波，注入电池产生交流恒流，同步采集电池两端电压，计算内阻。同时支持：

- 每 **1 分钟** 测量一次内阻
- **DS18B20** 每 **30 秒** 测温一次
- **UART 级联通讯**：多电池手拉手，UART2 作从机接收主机指令，UART1 作主机发送指令给下一级从机；主机可分配地址、获取所有从机数据（电压、电流、内阻、温度）
- **主从识别**：开机读取 Pin12 电平（内部上拉），低电平=主机，高电平=从机
- **非阻塞状态机架构**，禁止阻塞
- **异常数据识别算法**：识别充电/放电干扰导致的异常数据
- **相位校正**：补偿电路导致的注入电流与电压相位差
- **多点校准**：支持使用实际电阻校准
- **10kHz 同步采集**：与电流相位同步

输出到现有 Keil MDK 项目 `battery_re`，使用 C:\Keil_v5\UV4\UV4.exe 编译，确保编译通过。

## Source Materials

### Directory Overview

| Directory | Summary |
|-----------|---------|
| `battery_re/Core/Inc` | 项目头文件：`stm32g0xx_hal_conf.h`（HAL 配置）、`stm32g0xx_it.h`（中断声明） |
| `battery_re/Core/Src` | 项目源文件：`stm32g0xx_it.c`（中断服务）、`system_stm32g0xx.c`（系统初始化） |
| `battery_re/Drivers/STM32G0xx_HAL_Driver` | STM32G0 HAL 驱动库（Inc + Src） |
| `battery_re/Drivers/CMSIS` | CMSIS 核心、设备文件、DSP 库 |
| `battery_re/MDK-ARM` | Keil 项目文件（.uvprojx）、启动文件、构建输出 |
| `.document-reader/DS12991` | STM32G030x6/x8 数据手册 Markdown |
| `.document-reader/netlist` | 原理图网表文件 Markdown |
| `.document-reader/BOM` | BOM 文件 Markdown |
| `.document-reader/BOM_Board1_Schematic1_2026-05-23` | BOM 文件（第二份） |

### Key Files Inspected

- `user_req.txt` — 用户需求完整描述，含 20 条功能要求和实现步骤
- `Netlist_Schematic1_2026-05-25.tel` — 原理图网表，含所有网络连接
- `.document-reader/netlist/document.md` — 网表 Markdown 版
- `.document-reader/BOM/document.md` — BOM 表（元器件清单）
- `.document-reader/DS12991/document.md` — STM32G030 数据手册（5191 行）
- `battery_re/Core/Src/stm32g0xx_it.c` — 中断服务框架，含弱符号存根（SCHED_IncTick, UART_IRQHandler）
- `battery_re/Core/Src/system_stm32g0xx.c` — 系统时钟配置：HSE 8MHz → PLL → 64MHz SysClk
- `battery_re/Core/Inc/stm32g0xx_hal_conf.h` — HAL 模块配置，启用：ADC, TIM, UART, DMA, GPIO, EXTI, IWDG, RCC, FLASH, PWR, CORTEX
- `battery_re/MDK-ARM/battery_re.uvprojx` — Keil 项目配置，MCU=STM32G030F6Px, ARMCLANG V6.19, 64KB Flash, 8KB RAM
- `battery_re/MDK-ARM/startup_stm32g030xx.s` — 启动文件，堆=0x200, 栈=0x400
- `battery_re/MDK-ARM/fresh_build.log` — 上次成功构建日志（Code=5192）
- `battery_re/MDK-ARM/build_result.log` — 含 adc_acq.c 的构建日志（Code=10064）
- `battery_re/MDK-ARM/battery_re_build_gs.log` — 构建错误日志：GPIO_AF2_TIM3 未定义（STM32G030 中 AF2 宏名不同）
- `battery_re/MDK-ARM/battery_re.sct` — 链接分散加载文件（Flash: 0x08000000-0x00010000, RAM: 0x20000000-0x00002000）

## Task Requirements

### Functional behavior
1. **交流恒流注入**：TIM3_CH3 (PA7) 产生 1kHz 50% 占空比方波 → RC 滤波 → 正弦波 → 跟随器 → 运放恒流源 → 电池
2. **内阻测量**：同步采集注入电流（CURRENT_ADC）和电池两端电压（VOLT_ADC、RES_ADC），10kHz 采样率，与电流相位同步
3. **温度检测**：DS18B20 单总线（DQ），30 秒测量一次
4. **内阻计算周期**：每 1 分钟计算一次
5. **相位校正**：补偿电路导致的电流-电压相位差
6. **多点校准**：使用实际电阻对 ADC 测量值进行校准
7. **异常数据识别**：识别充电/放电干扰导致的异常数据并丢弃

### Interfaces and protocols
8. **UART1（主机口）**：TX=Pin20, RX=Pin1，作为主机与下一级从机通讯
9. **UART2（从机口）**：TX=Pin9, RX=Pin10，作为从机接收上一级主机指令
10. **级联协议自定义**：主机分配地址、以 1→2→3→…→N 轮询方式获取所有从机数据
11. **主从识别**：Pin12 (M_S)，开机输入检测，内部上拉；低电平=主机（GND），高电平=从机（悬空/3.3V）
12. **DS18B20 单总线**：Pin11 (DQ)

### Outputs and indicators
13. 内阻值、电压、注入电流、温度数据通过 UART 级联上传至最上级主机

### Timing and performance
14. 全部非阻塞状态机，禁止 HAL_Delay 等阻塞调用
15. **ADC 采样率**：10kHz，与 PWM 注入电流同步
16. **PWM 频率**：1kHz
17. **内阻计算**：每分钟一次
18. **温度测量**：每 30 秒一次

### Tests and acceptance criteria
19. 编译通过（0 Error, 0 Warning）
20. 协议设计文档和软件设计文档需同时输出

## Hardware Connection

### MCU / SoC
- **Part number**: STM32G030F6P6TR
- **Core / architecture**: ARM Cortex-M0+, 32-bit, up to 64 MHz
- **Package**: TSSOP-20 (6.5×4.4 mm)
- **Flash**: 32 KB, **SRAM**: 8 KB (with parity)
- **Datasheet**: DS12991 Rev 6

### Debug / Flash Interface
- **Protocol**: Serial Wire Debug (SW-DP)
- **Connector**: H5 (B-2100S04P-A110, 4-pin 2.54mm header)
  - Pin 1 (H5.1): 3.3V
  - Pin 2 (H5.2): ISOGND
  - Pin 3 (H5.3): SWDIO → MCU Pin 18 (PA13/SWDIO)
  - Pin 4 (H5.4): SWCLK → MCU Pin 19 (PF2/SWCLK)
- **Flash tool**: pyocd flash -t stm32f103c8（注意：hardware_config 中 flash 命令指向 STM32F103C8，实际应修正为 STM32G030F6）

### Peripheral Wiring

| Signal | MCU Pin | TSSOP-20 Pin | Target Device/Module | Direction | Notes |
|--------|---------|-------------|---------------------|-----------|-------|
| UART1_TX | PD2?/PAxx | Pin 20 | CN3.2 → U5 (CA-IS3721LS) isolation | Output | 主机 TX，经隔离输出到级联口 |
| UART1_RX | PD0?/PAxx | Pin 1 | CN3.1 → U5 isolation | Input | 主机 RX，经隔离输入 |
| UART2_TX | PA1? | Pin 9 | CN4.3 → R11 (10Ω) | Output | 从机 TX |
| UART2_RX | PA2? | Pin 10 | CN4.2 → R10 (10Ω) | Input | 从机 RX |
| DQ | PA3 | Pin 11 | H6.2 (DS18B20) → R6 (4.7kΩ pull-up to 3.3V) | Bidir | DS18B20 单总线 |
| M_S | PA4 | Pin 12 | R9 (100kΩ pull-up to ISOGND?) | Input | 主从识别，内部上拉 |
| TIM3_CH3 | PA7 | Pin 15 | R21 (100Ω) → RC滤波网络 | Output | 1kHz PWM 方波输出 |
| CURRENT_ADC | PA5 | Pin 13 | R52 (100kΩ) → U11 输出 | Input | 注入电流 ADC 采样 |
| RES_ADC | PA6 | Pin 14 | R38 (10kΩ)/C24 → U10 输出 | Input | 电池电压 ADC 采样 |
| VOLT_ADC | PA0 | Pin 8 | R4-1/R5-1 分压网络 | Input | 电池总电压 ADC 采样 |
| NRST | NRST | Pin 6 | U6 (reset circuit) | Input | 外部复位，内部上拉 |
| SWDIO | PA13/SWDIO | Pin 18 | H5.3 | Bidir | SWD 数据线 |
| SWCLK | PF2/SWCLK | Pin 19 | H5.4 | Input | SWD 时钟线 |
| VDD | VDD/VDDA | Pin 4 | 3.3V | Power | MCU 主电源 |
| VSS | VSS/VSSA | Pin 5 | ISOGND | Power | MCU 地（隔离地） |
| VSSA | VSS/VSSA | Pin 7 | ISOGND | Power | 模拟地 |

**注**：MCU 引脚号与 GPIO 名称的对应关系（基于 DS12991 Table 12 & Figure 4）：
- Pin 1 = PC14 (OSC32_IN) 但 UART1_RX 通常复用... [推断] 根据 netlist，U3-1.1 连接 UART1_RX 网络，但对 TSSOP-20 封装，Pin 1 是 PC14/OSC32_IN。UART1_RX 的 AF 在 STM32G030 上通常映射到 PA10 或 PD0/PD2，TSSOP-20 可能通过内部路由或 AF 映射实现。具体映射需参考 GPIO 复用表。
- Pin 8 = PA0 (VOLT_ADC, ADC_IN0)
- Pin 9 = PA1 (UART2_TX, AF=USART2_TX)
- Pin 10 = PA2 (UART2_RX, AF=USART2_RX)
- Pin 11 = PA3 (DQ, 用作 GPIO 单总线)
- Pin 12 = PA4 (M_S, 用作 GPIO 输入)
- Pin 13 = PA5 (CURRENT_ADC, ADC_IN5)
- Pin 14 = PA6 (RES_ADC, ADC_IN6)
- Pin 15 = PA7 (TIM3_CH3, AF=TIM3_CH3)
- Pin 18 = PA13 (SWDIO)
- Pin 19 = PF2 (SWCLK)
- Pin 20 = PD2? (UART1_TX)... 需确认

[推断] 实际 MCU 引脚功能需根据 STM32G030F6P6 TSSOP-20 的 alternate function 映射表确认，以下为推测：
- Pin 1 (PC14/OSC32_IN) 作为 UART1_RX — 可能使用 AF 映射或需要查看数据手册 AF 表确认
- Pin 20 作为 UART1_TX — 类似需要确认

### Power
- **Supply voltage**: 3.3V (VDD/VDDA) 和 3.3VA（模拟供电）
- **Regulator**: XC6206P332MR-G (U2-1) — 3.3V LDO
- **Isolation**: CA-IS3721LS (U5) — 数字隔离器，隔离 UART1 信号
- **隔离电源**: VPS8701B (U1-1) + 变压器 T1-1 — 隔离 DC-DC 转换器
- **1.65V 参考**: TLV431A (U1) — 分流稳压器产生 1.65V 中点参考
- **采样电阻**: R16 (0.1Ω) — 电流采样电阻
- **运放**: LM258DT (OP1) — 用于电压跟随/信号调理
- 其他运放 U8, U9, U10, U11 (SOP-8) — [推断] 用于恒流控制、信号放大、滤波等

### Uncertainties
- Pin 2, Pin 3, Pin 16, Pin 17 的 MCU 连接在网表中未以 U3-1.X 形式明确列出，可能未连接或连接在未解析的其他网络
- [推断] TSSOP-20 Pin 3 是 PF0（OSC_IN）/ NC 引脚，可能未使用
- UART1 的 TX/RX 在 TSSOP-20 上的具体引脚分配需要从 STM32G030 AF 表中确认（Pin 1 和 Pin 20 作为 UART1 需要验证）
- U8/U9/U10/U11 (SOP-8) 型号未在 BOM 中明确，[推断] 可能为通用运放如 LMV321/358 系列
- 隔离侧电源（+12V, 5V, 5VA）的直流路径未详细追踪

## Build, Flash, And Run Notes

### Build system
- **IDE**: Keil MDK v5 (μVision)
- **Compiler**: ArmClang V6.19 (ARMCLANG), ARM-ADS toolset
- **Project file**: `MDK-ARM/battery_re.uvprojx`
- **Build command**: `C:\Keil_v5\UV4\UV4.exe -j0 -b "MDK-ARM/battery_re.uvprojx" -o "MDK-ARM/build_log.txt"`
  - `-j0`: suppress status dialog
  - `-b`: batch build
  - Exit code 0 = success, 1 = warnings only, 2-20 = error, 21+ = fatal

### Build configuration
- **Defines**: `USE_HAL_DRIVER,STM32G030xx`
- **Include paths**: `../Core/Inc;../Drivers/STM32G0xx_HAL_Driver/Inc;../Drivers/STM32G0xx_HAL_Driver/Inc/Legacy;../Drivers/CMSIS/Device/ST/STM32G0xx/Include;../Drivers/CMSIS/Include;..\Drivers\CMSIS\DSP\Include`
- **Linker scatter**: `battery_re.sct` (Flash: 0x08000000, 64KB; RAM: 0x20000000, 8KB)
- **Optimization**: Level 1 (-O1)
- **Output name**: `battery_re`
- **Create HEX**: Yes (i32 combined)

### Flash command
- Configured in hardware_config: `pyocd flash -t stm32f103c8 build/firmware.elf`
- **⚠ WARNING**: Target MCU is STM32G030F6, not STM32F103C8. Flash command must be fixed.
- Correct command should be: `pyocd flash -t stm32g030f6 build/firmware.elf` (or path to axf/hex)
- Output artifact: `MDK-ARM/battery_re/battery_re.hex`

### Serial / debug observation
- **Port**: COM3 (configured), baud 115200
- UART can be used for debug output

### Host test command
- `python host_tests/smoke_test.py --port COM7 --baud 115200`

### Working directory
- `C:\Users\123\Desktop\neizu\tasknew`

### Existing project source files (to be preserved)
| File | Status | Notes |
|------|--------|-------|
| `Core/Src/system_stm32g0xx.c` | ✅ Exists | Clock: HSE 8MHz→PLL→64MHz, Flash 2WS |
| `Core/Src/stm32g0xx_it.c` | ✅ Exists | Weak stubs for SCHED_IncTick, UART_IRQHandler |
| `Core/Inc/stm32g0xx_hal_conf.h` | ✅ Exists | HAL modules configured |
| `Core/Inc/stm32g0xx_it.h` | ✅ Exists | Interrupt handler declarations |
| `MDK-ARM/startup_stm32g030xx.s` | ✅ Exists | Stack 0x400, Heap 0x200 |
| `Core/Src/main.c` | ❌ Missing | Must be created |
| `Core/Src/stm32g0xx_hal_msp.c` | ❌ Missing | Must be created (HAL MSP init) |

### Required new source modules (from requirements)
Based on user requirements, the following modules need to be created:
- `main.c` — 主入口，状态机调度
- `stm32g0xx_hal_msp.c` — HAL MSP 初始化（时钟、GPIO、DMA、NVIC）
- `tim_pwm.c/h` — TIM3 PWM 1kHz 配置
- `adc_acq.c/h` — ADC 同步采集（10kHz），含 DMA
- `ds18b20.c/h` — DS18B20 单总线驱动
- `uart_driver.c/h` — UART1/UART2 非阻塞驱动（中断+状态机）
- `uart_protocol.c/h` — 级联通讯协议
- `battery_measure.c/h` — 内阻计算、相位校正、校准
- `anomaly_detect.c/h` — 异常数据识别算法
- `scheduler.c/h` — 软件定时调度器
- `calibration.c/h` — 多点校准算法

### HAL modules enabled (from hal_conf.h)
ADC, TIM, UART, IWDG, GPIO, EXTI, DMA, RCC, FLASH, PWR, CORTEX

## Constraints And Risks

### Missing information
- **MCU TSSOP-20 引脚与 GPIO 复用映射未完全确定**：特别是 UART1_TX/RX 对应的具体 GPIO 和 AF 号，需从 STM32G030 数据手册 AF 表确认。Pin 1 (PC14) 和 Pin 20 作为 UART1 需要验证。
- **U8/U9/U10/U11 型号未知**：BOM 表中未填写型号，[推断] 为通用运放，需假定为 LMV321/358 等标准引脚排列。
- **DS18B20 连接细节**：网表确认 DQ 连接 PA3 (Pin 11)，通过 R6(4.7kΩ) 上拉到 3.3V，但供电连接未确认。
- **CN3/CN4 (4P 连接器)** 引脚定义不完全清晰。

### Unclear hardware details
- **隔离侧电路**：隔离电源 VPS8701B + 变压器产生隔离电源，但具体电压和路径未完全追踪。
- **RC 滤波网络**：TIM3_CH3 → RC 滤波 → 正弦波的具体元件未在网表中明确显示（可能由分立 RC 构成）。
- **恒流源电路**：具体由哪些运放（U8-U11）实现不明确。
- **上拉/下拉电阻**：M_S 引脚上 R9(100kΩ) 连接 ISOGND，但用户要求内部上拉 — 需确认。

### Uncertain build or flash commands
- **Flash 命令指向 STM32F103C8，实际 MCU 为 STM32G030F6**：必须修正 flash 命令。
- **CMake 命令**（hardware_config 中的 `cmake --build build`）与此 Keil 项目不匹配 — 实际使用 UV4.exe。

### Incomplete acceptance criteria
- 无明确的测试用例说明
- 无明确的通讯协议规范
- 无 ADC 校准精度要求的具体数值

### Truncated or unreadable files
- DS12991 数据手册 Markdown 转换为 5191 行，表格格式严重变形，引脚复用表难以精确读取
- user_req.txt 中部分字符编码损坏（如 "占空�?"）

### Real-hardware verification risks
- UART 级联需要多个硬件节点才能完整测试
- 异常数据识别算法需要真实充电/放电干扰环境验证
- 相位校正和校准算法需实际硬件调试

## Confidence Assessment

| Section | Confidence | Reason |
|---------|-----------|--------|
| Goal | High | 需求文档清晰明确，共 20 条要求 |
| Task Requirements | High | user_req.txt 列出了所有功能要求和实现步骤 |
| Hardware Connection | Medium | 网表和 BOM 提供了完整器件清单和网络连接，但 TSSOP-20 引脚复用需数据手册 AF 表确认，部分器件型号未知 |
| Build & Flash | Medium | Keil 项目配置完整，构建命令明确；但 flash 命令指向错误的 MCU 型号，CMake 命令与项目不匹配 |
| Constraints & Risks | Medium | 主要风险在于引脚复用映射和未完全明确的电路细节 |
```