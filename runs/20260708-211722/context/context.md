Now I have all the necessary information. Let me write the comprehensive context.md.

```markdown
# Build Context

## Goal

开发基于 STM32G030F6P6 (TSSOP-20) 的电池内阻测量系统，实现电池组级联通信和单体电池参数采集。要求：

- 使用 PWM 产生 1kHz 50% 方波，经模拟电路（RC 滤波器 + 跟随器 + 恒流源）生成正弦交流恒流注入电池
- 同步采集电池两端电压（10kHz 采样，与电流相位同步），计算电池内阻
- 支持 DS18B20 温度测量（30s 一次）
- 多电池手拉手 UART 级联：UART2 作为从机接收上级主机指令，UART1 作为主机发送指令给下级从机
- 主机自动分配地址，轮询所有从机数据（电压、电流、内阻、温度等）
- 开机通过 pin M_S 电平判断主/从身份
- 全部使用状态机实现，禁止阻塞
- 包含异常数据识别算法，抗充放电/逆变器干扰
- 支持注入电流与电压相位差校准，支持实际电阻多点校准
- 使用 Keil MDK-ARM (v5, ArmClang V6.19) 编译，输出到 `MDK-ARM/battery_re.uvprojx`

## Source Materials

### Directory Overview

| 目录 | 说明 |
|------|------|
| `battery_re/Core/Inc/` | HAL 配置文件 (`stm32g0xx_hal_conf.h`)、中断头文件 (`stm32g0xx_it.h`) |
| `battery_re/Core/Src/` | 源文件：`stm32g0xx_it.c`（中断服务框架）、`system_stm32g0xx.c`（系统时钟初始化） |
| `battery_re/Drivers/CMSIS/` | CMSIS 核心层、DSP 库 (`arm_cortexM0l_math.lib`)、设备头文件 |
| `battery_re/Drivers/STM32G0xx_HAL_Driver/` | STM32G0 HAL 驱动（ADC、RCC、TIM、UART、DMA、GPIO 等） |
| `battery_re/MDK-ARM/` | Keil 项目文件 (`battery_re.uvprojx`)、启动文件、编译输出 |
| `.document-reader/` | 硬件文档：BOM、网表、STM32G030 数据手册 |
| `.understand-anything/` | 项目理解工具的中间输出（分析缓存） |

### Key Files Inspected

- **`user_req.txt`** — 用户需求文档：功能描述、引脚分配、通信协议要求、编译方式
- **`Netlist_Schematic1_2026-05-25.tel`** — 电路网表：所有元件连接关系、MCU 引脚分配
- **`.document-reader/BOM/document.md`** — BOM 表：元件型号、封装、供应商
- **`.document-reader/BOM_Board1_Schematic1_2026-05-23/document.md`** — 另一版本 BOM（含 MCU 型号确认）
- **`.document-reader/netlist/document.md`** — 网表 Markdown 版（与 .tel 内容一致）
- **`.document-reader/DS12991/document.md`** — STM32G030x6/x8 数据手册目录/特征描述
- **`battery_re/MDK-ARM/battery_re.uvprojx`** — Keil 项目配置：MCU 型号、源文件列表、编译选项 (`USE_HAL_DRIVER,STM32G030xx`)、Include 路径
- **`battery_re/MDK-ARM/RTE/_battery_re/RTE_Components.h`** — 自动生成的 RTE 配置，定义 `CMSIS_device_header = "stm32g0xx.h"`
- **`battery_re/Core/Inc/stm32g0xx_hal_conf.h`** — HAL 模块选配：使能 `HAL_ADC_MODULE_ENABLED`、`HAL_TIM_MODULE_ENABLED`、`HAL_UART_MODULE_ENABLED`、`HAL_DMA_MODULE_ENABLED` 等
- **`battery_re/Core/Inc/stm32g0xx_it.h`** — 中断声明：`DMA1_Ch1_IRQHandler`、`ADC1_IRQHandler`、`TIM1_BRK_UP_TRG_COM_IRQHandler`、`TIM3_IRQHandler`、`TIM14_IRQHandler`、`USART1_IRQHandler`、`USART2_IRQHandler`
- **`battery_re/Core/Src/stm32g0xx_it.c`** — 中断服务框架：包含弱定义的 `SCHED_IncTick()` 和 `UART_IRQHandler(id)` 存根，供后续模块替换
- **`battery_re/Core/Src/system_stm32g0xx.c`** — 系统时钟配置：HSE 8MHz → PLL (×16, /2) → 64MHz SysClk；Flash 2 等待周期
- **`battery_re/MDK-ARM/battery_re.sct`** — 链接脚本：IROM 0x08000000 (64KB)，IRAM 0x20000000 (8KB)
- **`battery_re/MDK-ARM/build_log.txt`** — 编译日志：0 Error(s), 0 Warning(s)，已验证可编译通过
- **`battery_re/MDK-ARM/battery_re.BAT`** — 批处理编译命令，展示完整编译流程
- **`battery_re/MDK-ARM/startup_stm32g030xx.s`** — 启动文件（存在但未读取，标准 CMSIS 启动代码）

## Task Requirements

### 功能行为
- 产生 1kHz 50% PWM 方波（TIM3_CH3），经 RC 滤波 → 跟随器 → 运放恒流源，输出正弦交流注入电池
- 采样电阻 100mΩ (R16)，用于测量注入电流
- 10kHz ADC 同步采样电流电压（与 PWM 相位同步），计算内阻
- 每 1 分钟测量一次内阻
- DS18B20 一线式温度测量，每 30s 一次
- 多电池 UART 级联：UART2（从机接收上级指令）、UART1（主机发送指令给下级）
- 主机自动分配从机地址，轮询获取所有从机数据
- 开机判断主/从（pin M_S 电平），之后改为输入模式省电
- [推断] 协议自定义，需定义帧格式、地址分配、数据读写命令

### 接口和协议
- UART1：主机发送（TX）、从机接收（RX），经隔离芯片 CA-IS3721LS (U5) 到级联口
- UART2：从机接收（RX）、主机发送（TX），同样经隔离
- DQ (DS18B20)：单总线协议，30s 间隔
- M_S：主/从选择引脚（开机检测）
- 级联协议需自定义：地址分配命令、数据读取命令、可扩展数据字段

### 输出和指示
- [推断] 无明确 LED/显示指示需求，仅通过 UART 级联输出数据

### 定时和性能
- PWM：1kHz (周期 1ms)
- ADC 采样：10kHz (周期 100µs)，与电流相位同步
- 内阻测量周期：1 分钟
- 温度测量周期：30s
- MCU 主频：64MHz (SysClk)
- 禁止阻塞，全部状态机实现

### 测试和接受标准
- 编译 0 error 0 warning
- 需验证 UART 级联通信、内阻测量精度、温度读取等功能
- 需设计异常数据识别算法应对充放电干扰

## Hardware Connection

### MCU / SoC
- **Part number**: STM32G030F6P6TR (U3-1)
- **Core / architecture**: ARM Cortex-M0+, 32-bit, up to 64 MHz
- **Package**: TSSOP-20 (6.5×4.4 mm), pin pitch 0.65mm
- **Flash**: 32 KB (on-chip)
- **SRAM**: 8 KB (with HW parity)
- **Datasheet**: DS12991 Rev 6

### Debug / Flash Interface
- **Protocol**: SWD (Serial Wire Debug) — 2 pins
- **Connector**: H5 (B-2100S04P-A110, 4-pin header 2.54mm)
  - H5.1 = 3.3V
  - H5.2 = ISOGND
  - H5.3 = SWDIO (U3-1.18)
  - H5.4 = SWCLK (U3-1.19)
- **Required tools**: J-Link / ST-Link (via SWD), or Keil ULINK

### Peripheral Wiring

从网表提取的 MCU 引脚连接（STM32G030F6P6 TSSOP-20）：

| Signal | MCU Pin | TSSOP-20 Pin | Target Device/Module | Direction | Notes |
|--------|---------|-------------|---------------------|-----------|-------|
| UART1_RX | PB1 | 1 | CN4.3 (级联口) via R11(10Ω) | IN | 作为主机接收下级从机数据 |
| — | PF2 | 2 | $2N1217 (CN3.1→U5.1→U3.2) | — | [推断] 通过隔离器U5的通道，连接到CN3.1 |
| — | PB3 | 3 | 连接U3.2 (可能是另一个MCU或逻辑) | — | [推断] 未在网表中直接连接到U3-1 |
| VDD | — | 4 | 3.3V | Power | MCU 供电 |
| VSS | — | 5 | ISOGND | Power | 隔离地 |
| NRST | NRST | 6 | U6.1 (电容到GND) | IN | 外部复位，带RC |
| VSSA | — | 7 | ISOGND | Power | 模拟地 |
| VOLT_ADC | PA7 | 8 | 运放输出 (R4-1→R5-1分压) | IN | ADC1_IN7，采集电池两端电压 |
| UART2_TX | PA2 | 9 | CN4.1 via R8(10Ω)→U5.6(隔离器)→CN3.2 | OUT | 从机向主机发送数据 |
| UART2_RX | PA3 | 10 | CN4.2 via R7(10Ω)→U5.7(隔离器)→CN3.3 | IN | 从机接收主机指令 |
| DQ | PA6 | 11 | H6.2 (DS18B20 接口) via R6(4.7kΩ) 上拉到3.3V | IN/OUT | OneWire 数据线 |
| M_S | PA5 | 12 | R9(100kΩ) 上拉到3.3V | IN | 主/从选择：高=主机，低=从机；开机检测 |
| CURRENT_ADC | PA1 | 13 | U11.1 (运放输出) via R52(100kΩ) | IN | ADC1_IN1，采集注入电流（采样电阻100mΩ） |
| RES_ADC | PA0 | 14 | U10.7 (运放输出) via R38(10kΩ) | IN | ADC1_IN0，采集内阻相关电压 |
| TIM3_CH3 | —[注] | 15 | R21(100kΩ)→RC滤波网络→OP1(运放) | OUT | 1kHz 50% PWM 输出，产生交流恒流 |
| — | — | 16 | NC (未连接) | — | 空脚 |
| — | — | 17 | NC (未连接) | — | 空脚 |
| SWDIO | PA10 | 18 | H5.3 (SWD 调试接口) | IN/OUT | SWD 数据线 |
| SWCLK | PA9 | 19 | H5.4 (SWD 调试接口) | IN | SWD 时钟线 |
| UART1_TX | PA4 | 20 | CN4.2-3 via R10(10Ω)→U5.2→CN3.2 | OUT | 作为主机发送指令给下级 |

> [注] STM32G030F6P6 TSSOP20 封装 Pin 15 应为 PB0（AF: TIM3_CH3, USART1_CK, TIM1_CH2N）。网表明确标注 `TIM3_CH3` 连接到 R21。TIM1_BRK_UP_TRG_COM_IRQHandler 在项目中存在但 TIM1 未在 HAL 配置中使能。

### 关键外部元件

| 元件 | 型号 | 功能 |
|------|------|------|
| OP1 | LM258DT (SOIC-8) | 双运放，用于 RC 滤波后的跟随器和恒流驱动 |
| U5 | CA-IS3721LS (SOIC-8) | 双通道数字隔离器，用于 UART 级联隔离 |
| U1 | TLV431AIDBZR (SOT-23-3) | 可调精密并联稳压器，产生 1.65V 参考电压 |
| U1-1 | VPS8701B (SOT-23-6) | DC-DC 转换器，产生隔离电源 |
| U2-1 | XC6206P332MR-G (SOT-23-3) | 3.3V LDO 稳压器 |
| U8/U9/U10/U11 | SOP-8 (未指定型号) | [推断] 运放或比较器，用于信号调理 |
| T1-1 | VPT87DFB01B | 变压器，用于隔离电源 |
| R16 | 0.1Ω (0805) | 电流采样电阻 |
| D1 | SMAJ15CA (SMA) | TVS 保护管 |
| D2-1/D3-1 | RB160M-30 (SOD-123) | 肖特基二极管 |
| F1-1 | 0603L050YR | PTC 自恢复保险丝 |
| CN1/CN2 | HT396V-3.96-2P | 电池接线端子（2-pin, 3.96mm间距） |
| CN3/CN4 | KF2EDGV-2.54-4P (xh2.54-4p) | 级联通信接口（4-pin） |
| H6 | xh2.54-3p | DS18B20 接口（3-pin） |

### 电源
- **外部输入**: +12V (CN1.1/CN2.1)
- **隔离电源**: VPS8701B (U1-1) + 变压器 (T1-1) 产生隔离 5V/3.3V
- **非隔离 3.3V**: XC6206P332MR-G (U2-1) LDO
- **3.3VA**: 模拟供电 (隔离侧)
- **1.65V 参考**: TLV431AIDBZR (U1) + 电阻分压网络产生
- **GND**: 非隔离地
- **ISOGND**: 隔离地（电池侧）

### 不确定项
- U8/U9/U10/U11 的具体型号未在 BOM 中标注（SOP-8 封装），[推断] 为通用运放（如 LMV321 或类似）
- TIM1 中断已声明 (`TIM1_BRK_UP_TRG_COM_IRQHandler`) 但 TIM1 未在 HAL 配置中使能 — 可能是 TIM3 的别名中断（G0 系列 TIM1 和 TIM3 共享中断向量？）或代码残留
- 网表中的 `U3.2` 指另一个 MCU 还是标签？从连接看，`$2N1217` 同时连接 `CN3.1`、`U3.2`、`U5.1`，而 `U3-1` 是 MCU。`U3.2` 可能是 U3-1 的 pin 2 或另一个器件 — [推断] 可能是共用一个信号

## Build, Flash, And Run Notes

- **Build system**: Keil MDK-ARM v5 (µVision), ArmClang V6.19
- **Project file**: `MDK-ARM/battery_re.uvprojx`
- **MCU**: STM32G030F6Px (Cortex-M0+, 64KB Flash, 8KB RAM)
- **Preprocessor defines**: `USE_HAL_DRIVER,STM32G030xx`
- **Include paths**:
  - `../Core/Inc`
  - `../Drivers/STM32G0xx_HAL_Driver/Inc`
  - `../Drivers/STM32G0xx_HAL_Driver/Inc/Legacy`
  - `../Drivers/CMSIS/Device/ST/STM32G0xx/Include`
  - `../Drivers/CMSIS/Include`
  - `..\Drivers\CMSIS\DSP\Include`
- **Build command**: `C:\Keil_v5\UV4\UV4.exe -j0 -b "MDK-ARM/battery_re.uvprojx" -o "MDK-ARM/build_log.txt"`
- **Flash command**: `pyocd flash -t stm32f103c8 build/firmware.elf`（硬件配置中指定，但实际 MCU 为 STM32G030F6P6 — **可能需修改为 `-t stm32g030f6`**）
- **Serial port**: COM3 (project_root config), COM7 (host test)
- **Baud rate**: 115200
- **Output artifacts**: `battery_re/battery_re.axf`, `battery_re/battery_re.hex`
- **Linker script**: 内置在 .uvprojx 中（IROM: 0x08000000, 64KB; IRAM: 0x20000000, 8KB）
- **DSP library**: `..\Drivers\CMSIS\DSP\Lib\ARM\arm_cortexM0l_math.lib`（已链接）
- **Required toolchain**: Keil MDK v5.xx with ARM Compiler 6.19
- **Working directory**: project root

### 现有框架代码说明
已存在的框架代码（`stm32g0xx_it.c`、`system_stm32g0xx.c`）结构：
- `main.c` **不存在** — 需要创建
- `stm32g0xx_hal_msp.c` **不存在** — 需要创建（或从 .map 引用看，需包含 HAL_MspInit、HAL_ADC_MspInit、HAL_TIM_Base_MspInit、HAL_TIM_PWM_MspInit、HAL_UART_MspInit）
- `stm32g0xx_it.c` 包含弱定义存根 `SCHED_IncTick()` 和 `UART_IRQHandler(id)`，供后续模块替换
- `system_stm32g0xx.c` 配置 HSE 8MHz → PLL → 64MHz SysClk

## Constraints And Risks

- **main.c 和 main.h 不存在** — 完全需要新建，但 .uvprojx 已引用 `../Core/Src/main.c` 和 `../Core/Inc/main.h`
- **stm32g0xx_hal_msp.c 不存在** — 需要创建，.map 显示引用 `HAL_ADC_MspInit`、`HAL_TIM_Base_MspInit`、`HAL_TIM_PWM_MspInit`、`HAL_UART_MspInit`
- U8/U9/U10/U11 型号未知 — 影响模拟前端信号链路理解
- 网表中 `U3.2`（非 `U3-1.2`）含义模糊 — 可能是不同元件 U3 的 pin 2
- 模拟电路的具体拓扑（RC 滤波器参数、运放连接方式）需从网表进一步推导
- Flash 命令中的 target 是 `stm32f103c8` 但实际 MCU 是 `STM32G030F6P6` — 需修正
- 用户需求提到"所有禁止阻塞，全部用状态机" — 需要设计完善的调度器
- 异常数据识别算法需仔细设计，无现有参考
- 自定义 UART 级联协议需完全自主设计
- 相位同步 ADC 采样（10kHz 与 1kHz PWM 同步）需要精确的定时触发配置

## Confidence Assessment

| Section | Confidence | Reason |
|---------|-----------|--------|
| Goal | High | 用户需求文档非常详细，目标明确 |
| Task Requirements | High | 明确列出功能、引脚、通信、编译要求 |
| Hardware Connection | Medium | MCU 引脚连接从网表完全确定，但 U8-U11 型号未知，模拟电路细节需进一步推导 |
| Build & Flash | High | .uvprojx、.sct、编译日志都确认了构建系统，但 flash 命令的 target 可能需修正 |
| Constraints & Risks | Medium | main.c/msp.c 缺失是被预期需要新建的，但模拟芯片型号不明确构成风险 |
```