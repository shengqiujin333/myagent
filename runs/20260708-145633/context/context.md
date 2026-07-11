# Build Context

## Goal

完成电池内阻测量系统的嵌入式固件开发。核心功能：

- **MCU**: STM32G030F6P6 (TSSOP-20, Cortex-M0+, 32KB Flash, 8KB RAM)
- **PWM生成交流恒流**: TIM3产生1kHz、50%占空比方波 → RC滤波成正弦波 → 运放恒流源 → 注入电池
- **电池内阻测量**: 10kHz采样注入电流产生的电池两端电压，与电流相位同步，计算内阻
- **温度测量**: DS18B20 (DQ pin)，30s测量一次
- **UART级联通讯**: 多个电池模块手拉手，USART1为主机(发送指令给下一级)，USART2为从机(接收上一级指令)
- **主从机识别**: Pin12 (M_S) 上拉检测 — 低电平为主机，高电平为从机（开机判断一次后改输入）
- **完全状态机实现**，禁止阻塞
- **异常数据识别算法**：抗充电/放电干扰
- **相位校正**：对电路导致的注入电流与电压相位差进行补偿
- **多点校准**：使用实际电阻对测量值进行校准
- **任务输出**：直接写入 `battery_re` 工程，使用 Keil MDK-ARM 编译

## Source Materials

### Directory Overview

| Directory | Summary |
|-----------|---------|
| `battery_re/Core/Inc` | HAL配置文件、中断头文件 |
| `battery_re/Core/Src` | 中断实现、系统时钟初始化（已存在stm32g0xx_it.c, system_stm32g0xx.c） |
| `battery_re/Drivers/STM32G0xx_HAL_Driver` | STM32G0 HAL驱动库完整源代码 |
| `battery_re/Drivers/CMSIS` | CMSIS核心、DSP库(含arm_cortexM0l_math.lib)、STM32G0xx设备文件 |
| `battery_re/MDK-ARM` | Keil项目文件、启动文件、编译日志 |
| `.document-reader/BOM` | BOM物料清单 Markdown 摘要 |
| `.document-reader/BOM_Board1_Schematic1_2026-05-23` | 同一BOM的副本 |
| `.document-reader/DS12991` | STM32G030x6/x8 数据手册 Markdown 转换（298913字节） |
| `.document-reader/netlist` | 网表文件 Markdown 摘要（含$PACKAGES/$NETS） |

### Key Files Inspected

| 文件 | 相关性 |
|------|--------|
| `user_req.txt` | 用户需求全文 — 功能、引脚定义、通讯协议、实现要求 |
| `.document-reader/netlist/document.md` | 网表 — 所有网络连接、封装信息、MCU引脚连接关系 |
| `.document-reader/BOM/document.md` | BOM表 — 全部元器件清单、型号、封装 |
| `.document-reader/DS12991/document.md` | STM32G030数据手册 — 功能概述、电气特性、封装信息 |
| `battery_re/Core/Inc/stm32g0xx_hal_conf.h` | HAL模块使能配置：ADC, TIM, UART, DMA, GPIO, EXTI, RCC, FLASH, PWR, IWDG, CORTEX |
| `battery_re/Core/Inc/stm32g0xx_it.h` | 中断声明：DMA1_CH1, ADC1, TIM1_BRK_UP_TRG_COM, TIM3, TIM14, USART1, USART2 |
| `battery_re/Core/Src/stm32g0xx_it.c` | 中断实现 — 含弱符号存根(SCHED_IncTick, UART_IRQHandler)供后续模块替换 |
| `battery_re/Core/Src/system_stm32g0xx.c` | 系统时钟: HSE 8MHz → PLL(x16,/2) → SysClk=64MHz |
| `battery_re/MDK-ARM/battery_re.uvprojx` | Keil项目配置：STM32G030F6Px, ArmClang V6.19, Flash 64KB, RAM 8KB |
| `battery_re/MDK-ARM/startup_stm32g030xx.s` | 启动文件：堆栈配置(Stack=0x400, Heap=0x200)，中断向量表 |
| `battery_re/MDK-ARM/build_log.txt` | 编译成功日志：0 Error(s), 0 Warning(s), Code=3432 RO-data=288 RW-data=12 ZI-data=1660 |
| `Netlist_Schematic1_2026-05-25.tel` | 原始网表文件(.tel格式)，与document.md内容相同 |

### 缺失文件（需创建）

- `Core/Src/main.c` — uvprojx中已引用但不存在
- `Core/Src/stm32g0xx_hal_msp.c` — uvprojx中已引用但不存在

## Task Requirements

### 功能行为

1. **交流恒流注入**: TIM3_CH3 (Pin15) 产生1kHz/50%方波 → RC滤波 → 正弦波 → 跟随器 → 运放恒流 → 注入电池。采样电阻=100mΩ(R16)
2. **电压/电流/内阻测量**: ADC以10kHz采样率、与注入电流相位同步，采集注入电流在电池两端产生的电压。需校正电路导致的相位差
3. **温度测量**: DS18B20 (DQ, Pin11)，30s测量一次
4. **UART级联通讯**:
   - USART1(Pins1/20): 主机模式，向下一级从机发送指令、分配地址、读取数据
   - USART2(Pins9/10): 从机模式，接收上一级主机指令
   - 协议自定义，支持电压、电流、内阻、温度等可扩展数据
5. **主从识别**: Pin12(M_S)开机检测 — 内部上拉后若为低电平则为主机，高电平为从机。检测后切换为输入模式省电
6. **状态机驱动**: 整体禁止阻塞，全部状态机实现
7. **异常数据识别**: 抗充电/放电干扰算法，异常数据丢弃

### 接口与协议

- **通讯接口**: USART1(主机)、USART2(从机)，通过CA-IS3721LS隔离
- **通讯协议**: 自定义级联协议，主机分配地址，轮询读取所有从机数据
- **传感器**: DS18B20单总线(OneWire)协议
- **ADC**: 输入 — VOLT_ADC(Pin8), CURRENT_ADC(Pin13), RES_ADC(Pin14)

### 输出与指示

- M_S(Pin12) — 主从状态指示
- 数据通过UART上报

### 测试与验收

- Keil编译通过：`UV4.exe -j0 -b "MDK-ARM/battery_re.uvprojx" -o "MDK-ARM/build_log.txt"`
- 硬件实际运行测试

## Hardware Connection

### MCU / SoC

| 属性 | 值 |
|------|------|
| Part number | STM32G030F6P6TR |
| Core / architecture | Arm Cortex-M0+, 32-bit |
| Package | TSSOP-20 (6.5×4.4mm, 0.65mm pitch) |
| Flash / SRAM | 32KB / 8KB (with parity) |
| Max frequency | 64 MHz |
| Operating voltage | 2.0–3.6 V (板上用XC6206P332MR 3.3V LDO供电) |
| Debug interface | SWD (SWCLK/SWDIO on H5 connector) |

### Debug / Flash Interface

| 属性 | 值 |
|------|------|
| Protocol | SWD (Serial Wire Debug) |
| Connector | H5 (B-2100S04P-A110, 4-pin header) |
| Pinout | H5.1=3.3V, H5.2=GND, H5.3=SWDIO(Pin18), H5.4=SWCLK(Pin19) |
| Required tools | J-Link / ST-Link / pyOCD (配置为pyocd flash -t stm32f103c8，但实际目标为stm32g030f6) |

### Peripheral Wiring

| 信号 | MCU引脚 | 目标器件 | 方向 | 说明 |
|------|---------|---------|------|------|
| UART1_RX | Pin 1 | → R11 → U5.7(OUT1) → CN3 | 输入 | USART1接收(从隔离器来) |
| UART1_TX | Pin 20 | → R10 → U5.6(OUT2) → CN3 | 输出 | USART1发送(经隔离器) |
| UART2_RX | Pin 10 | → R7 → U5.7(OUT1) → CN4 | 输入 | USART2接收(经隔离器) |
| UART2_TX | Pin 9 | → R8 → U5.6(OUT2) → CN4 | 输出 | USART2发送(经隔离器) |
| VOLT_ADC | Pin 8 | 电池电压采样网络(R4-1,R5-1分压) | 输入 | ADC输入，测量电池电压 |
| CURRENT_ADC | Pin 13 | → U11.1(运放输出) | 输入 | ADC输入，测量注入电流 |
| RES_ADC | Pin 14 | → U10.7(运放输出) | 输入 | ADC输入，测量电压响应 |
| TIM3_CH3 | Pin 15 | → R21 → PWM驱动电路 | 输出 | 1kHz/50%方波，产生交流恒流 |
| DQ | Pin 11 | → R6(4.7k上拉) → H6.2(DS18B20) | 双向 | DS18B20单总线数据线 |
| M_S | Pin 12 | → R9(100k上拉) | 输入 | 主从识别：检测电平 |
| NRST | Pin 6 | 外部复位电路(U6) | 输入 | 复位引脚 |
| SWDIO | Pin 18 | H5.3 | 双向 | SWD数据线 |
| SWCLK | Pin 19 | H5.4 | 输入 | SWD时钟线 |
| VDD | Pin 4 | 3.3V供电 | 电源 | VDD/VDDA |
| VSS | Pins 5,7 | GND | 地 | VSS/VSSA |

**注**: MCU引脚编号 (Pin 1~20) 与 STM32G030F6P6 TSSOP-20 物理引脚对应。功能分配依据网表信号名推断。

### 关键外围器件

| 器件 | 型号 | 功能 |
|------|------|------|
| LDO | XC6206P332MR (U2-1) | 5V→3.3V稳压 |
| 运放 | LM258DT (OP1) | 信号跟随/放大 |
| 隔离器 | CA-IS3721LS (U5) | UART信号隔离，2通道正向 |
| 运放4x | SOP-8 (U8,U9,U10,U11) | 测量电路运放(型号未标注) |
| 采样电阻 | 0.1Ω/0805 (R16) | 电流采样电阻 |
| 变压器 | VPT87DFB01B (T1-1) | 隔离电源变压器 |
| TVS | SMAJ15CA (D1-1) | 过压保护 |
| 自恢复保险 | 0603L050YR (F1-1) | 过流保护 |
| 肖特基 | RB160M-30 (D2-1,D3-1) | 整流 |
| 基准 | TLV431AIDBZR (U1) | 1.65V基准电压产生 |
| 开关电源 | VPS8701B (U1-1) | 隔离DC-DC |
| DS18B20 | 外接(H6) | 温度传感器 |

### 连接器

| 连接器 | 类型 | 用途 |
|--------|------|------|
| CN1, CN2 | HT396V-3.96-2P | 电池电源接入 (+12V, GND) |
| CN3 | KF2EDGV-2.54-4P | UART级联通讯口(隔离侧) |
| CN4 | KF2EDGV-2.54-4P | UART级联通讯口(隔离侧) |
| H1,H2,H3,H4 | 2.54mm 1x1P | 电池连接 (RES_SENSOR+/-, GND, 信号) |
| H5 | B-2100S04P-A110 4P | SWD调试接口 |
| H6 | 2.54mm 1x3P | DS18B20接口 |

### Power

| 属性 | 值 |
|------|------|
| Supply voltage | 12V (通过CN1/CN2输入) |
| Regulator | XC6206P332MR (3.3V LDO, SOT-23-3) |
| 隔离电源 | VPS8701B + VPT87DFB01B 变压器 → 产生隔离5V/3.3V |
| 模拟电源 | 5VA → OP1(LM258)供电 |
| 参考电压 | 1.65V (TLV431产生) |

## Build, Flash, And Run Notes

| 属性 | 值 |
|------|------|
| Build system | Keil MDK-ARM v5 (UV4) |
| Toolchain | ArmClang V6.19 (ARM Compiler 6) |
| 编译命令 | `C:\Keil_v5\UV4\UV4.exe -j0 -b "MDK-ARM/battery_re.uvprojx" -o "MDK-ARM/build_log.txt"` |
| 编译参数 | -j0(无弹窗), -b(增量编译), 退出码0=成功, 1=有警告, 2+=错误 |
| 预定义宏 | `USE_HAL_DRIVER, STM32G030xx` |
| 头文件路径 | `../Core/Inc; ../Drivers/STM32G0xx_HAL_Driver/Inc; ../Drivers/STM32G0xx_HAL_Driver/Inc/Legacy; ../Drivers/CMSIS/Device/ST/STM32G0xx/Include; ../Drivers/CMSIS/Include; ..\Drivers\CMSIS\DSP\Include` |
| DSP库 | `..\Drivers\CMSIS\DSP\Lib\ARM\arm_cortexM0l_math.lib` |
| Flash命令 | `pyocd flash -t stm32f103c8 build/firmware.elf` (配置中目标为stm32f103c8，实际应为stm32g030f6) |
| Serial监视 | COM3, 115200 baud |
| Host测试 | `python host_tests/smoke_test.py --port COM7 --baud 115200` |
| 输出目录 | `battery_re/` |
| 输出文件 | `battery_re.axf` (ELF), `battery_re.hex` (Intel HEX) |
| 内存映射 | Flash: 0x08000000 (64KB), RAM: 0x20000000 (8KB) |
| 堆栈配置 | Stack=0x400 (1KB), Heap=0x200 (512B) |
| 已有源文件 | `startup_stm32g030xx.s`, `stm32g0xx_it.c`, `system_stm32g0xx.c` + HAL驱动源文件 |
| 项目组结构 | Application/MDK-ARM, Application/User/Core, Drivers/STM32G0xx_HAL_Driver, Drivers/CMSIS |

### 已使能HAL模块

ADC, IWDG, TIM, UART, GPIO, EXTI, DMA, RCC, FLASH, PWR, CORTEX

### 已有中断处理程序(含弱符号存根)

| 中断 | 处理程序 |
|------|---------|
| SysTick | HAL_IncTick() + SCHED_IncTick() [weak] |
| DMA1_Ch1 | HAL_DMA_IRQHandler(&hdma_adc1) |
| ADC1 | HAL_ADC_IRQHandler(&hadc1) |
| TIM3 | HAL_TIM_IRQHandler(&htim3) |
| TIM1_BRK_UP_TRG_COM | HAL_TIM_IRQHandler(&htim3) (注意：应改为&htim1？) |
| TIM14 | HAL_TIM_IRQHandler(&htim14) |
| USART1 | UART_IRQHandler(1) [weak] |
| USART2 | UART_IRQHandler(2) [weak] |

## Constraints And Risks

### 缺失信息

- **main.c 和 stm32g0xx_hal_msp.c**: 已在 uvprojx 中引用但文件不存在，需创建
- **DS18B20 具体连接**: DQ连接已知，但H6连接器3脚定义不完全明确（H6.1=3.3V, H6.2=DQ, H6.3=GND 为合理推断）
- **未标注型号的运放**: U8,U9,U10,U11 (SOP-8) 型号未知，无法确定具体规格
- **ADC通道映射**: VOLT_ADC, CURRENT_ADC, RES_ADC 对应的ADC内部通道号需根据STM32G030参考手册确定
- **CA-IS3721LS详细连接**: 隔离器方向与UART TX/RX匹配关系需确认

### 不确定的硬件细节

- **TIM3_CH3的物理GPIO端口**: Pin 15 确认为PA0或PB0等（需查手册确认TIM3_CH3输出映射）
- **UART1/UART2的GPIO复用功能**: Pins 1/20 和 9/10 的具体GPIO端口号与AF配置需查手册确认
- **调试接口工具**: pyOCD命令中 `-t stm32f103c8` 与目标MCU (STM32G030F6) 不匹配，需修正
- **1.65V基准网络**: R3(680Ω→实际660Ω), R4(820Ω) 分压产生的1.65V供给TLV431和多个电阻分压网络

### 风险

- 全部状态机实现要求较高设计复杂度
- 10kHz ADC采样与1kHz PWM的相位同步需要定时器精准触发
- 异常数据识别算法需要仔细设计以区分真实测量值和充放电干扰
- 级联UART协议需要自定义，且需支持地址分配和扩展数据

## Confidence Assessment

| Section | Confidence | Reason |
|---------|-----------|--------|
| Goal | High | 用户需求明确，目标清晰 |
| Task Requirements | High | 需求文档完整，功能列表详细 |
| Hardware Connection | Medium | 网表提供了完整连接信息，但部分器件型号未知，GPIO端口号需查手册确认 |
| Build & Flash | High | uvprojx文件完整，编译已验证通过，工具链明确 |
| Constraints & Risks | High | 缺失和风险点已识别 |