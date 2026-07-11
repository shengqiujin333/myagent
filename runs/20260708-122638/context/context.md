Now I have enough information. Let me write the context.md.

```markdown
# Build Context

### Goal
完成基于 STM32G030F6P6 (TSSOP-20) 的电池内阻测量系统固件。系统通过 PWM 产生 1kHz 50% 占空比方波，经 RC 滤波和运放恒流源电路向电池注入交流电流，同步测量电池两端电压和注入电流以计算内阻。每 1 分钟测量一次。多个电池模块通过 USART 级联通信（主机-从机架构），支持动态地址分配、温度测量 (DS18B20)、异常数据识别。所有代码放入现有 Keil MDK-ARM 工程并编译通过。

### Source Materials

### Directory Overview

| 目录 | 说明 |
|------|------|
| `battery_re/Core/Inc` | 存放 HAL 配置文件 (`stm32g0xx_hal_conf.h`)、中断头文件 (`stm32g0xx_it.h`)。**尚无 `main.h`，需创建。** |
| `battery_re/Core/Src` | 存放系统文件 (`system_stm32g0xx.c`)、中断实现 (`stm32g0xx_it.c`)。**尚无 `main.c` 或 `stm32g0xx_hal_msp.c`，需创建。** |
| `battery_re/Drivers/STM32G0xx_HAL_Driver` | STM32G0 HAL/LL 驱动源码和头文件。启用的 HAL 模块见下文。 |
| `battery_re/Drivers/CMSIS` | CMSIS 核心和 DSP 库 (`arm_cortexM0l_math.lib`)。 |
| `battery_re/MDK-ARM` | Keil uVision 工程文件 (`battery_re.uvprojx`)、启动文件、构建脚本、链接脚本 (`battery_re.sct`)、构建日志。 |
| `.document-reader` | 硬件文档：网表 (TEL)、BOM (Excel)、MCU 数据手册 (DS12991)。 |
| `.understand-anything` | 自动分析工具的中间产物。 |

### Key Files Inspected

- `user_req.txt` — 项目核心需求：功能描述、引脚分配、通信协议要求、编译方式 (Keil UV4)。
- `Netlist_Schematic1_2026-05-25.tel` — 完整网表文件。确认所有 MCU 引脚连接、电源网络、元器件互联。
- `.document-reader/BOM_Board1_Schematic1_2026-05-23/document.md` — BOM 表，确认所有元器件型号、封装、供应商。
- `.document-reader/netlist/document.md` — 网表 Markdown 格式副本。
- `.document-reader/DS12991/chunks/*` — STM32G030x6/x8 数据手册节选。部分表格（引脚分配表）未被正确提取，需参考 ST 官方文档辅助确认。
- `battery_re/Core/Src/system_stm32g0xx.c` — 时钟配置：HSE 8MHz → PLL → 64MHz SysClk。Flash 等待周期 = 2，预取使能。
- `battery_re/Core/Src/stm32g0xx_it.c` — 中断服务框架。包含外设句柄声明（ADC、TIM3、TIM14、DMA、UART1/2），弱符号存根 (`SCHED_IncTick`, `UART_IRQHandler`) 供后续模块替换。
- `battery_re/Core/Inc/stm32g0xx_hal_conf.h` — HAL 模块选择。启用：ADC、TIM、UART、GPIO、DMA、RCC、FLASH、PWR、CORTEX、EXTI、IWDG。禁用：I2C、SPI、RTC 等。
- `battery_re/Core/Inc/stm32g0xx_it.h` — 中断函数声明。包含 DMA1_CH1、ADC1、TIM1_BRK_UP_TRG_COM、TIM3、TIM14、USART1/2。
- `battery_re/MDK-ARM/battery_re.uvprojx` — Keil 项目配置。设备：STM32G030F6Px。编译器：ArmClang V6.19。定义宏：`USE_HAL_DRIVER,STM32G030xx`。Flash: 0x08000000, 64KB。RAM: 0x20000000, 8KB。
- `battery_re/MDK-ARM/startup_stm32g030xx.s` — 启动文件。Stack: 0x400, Heap: 0x200。
- `battery_re/MDK-ARM/battery_re.sct` — 分散加载文件。与启动文件匹配。
- `battery_re/MDK-ARM/battery_re.BAT` — 构建批处理文件。展示完整编译和链接命令链。
- `battery_re/MDK-ARM/build_log.txt` — **最近一次成功构建日志** (0 errors)。Program Size: Code=3432, RO-data=288, RW-data=12, ZI-data=1660。
- `battery_re/MDK-ARM/battery_re_build_gs.log` — **存在编译错误**：`GPIO_AF2_TIM3` 未声明（`stm32g0xx_hal_msp.c:124`）。需修正为正确宏名。
- `battery_re/MDK-ARM/battery_re_build_gs2.log` — 重建成功日志 (0 errors)。Program Size: Code=6528, RO-data=288, RW-data=12, ZI-data=1580。

### Task Requirements

**功能行为：**
- PWM 产生 1kHz 50% 占空比方波 → RC 滤波 → 运放恒流 → 向电池注入交流电流。
- 同步 10kHz ADC 采集电池两端电压和注入电流，与电流相位同步。
- 对电路导致的电流-电压相位差进行校准。
- 使用实际电阻对测量结果进行多点校准。
- 每 1 分钟测量一次电池内阻。
- 异常数据识别算法：排除充放电/逆变器干扰导致的异常值。

**接口和协议：**
- **USART1 (主机端)**：PB3=TX, PA10=RX。主机通过 UART1 向下一从机发送指令。
- **USART2 (从机端)**：PA1=TX, PA2=RX。经 U5 (CA-IS3721LS 数字隔离器) 连接到外部 CN3 连接器。从机接收上一级指令。
- **级联通信**：一组多个电池模块通过 UART 手拉手级联。主机可分配地址、读取所有从机的电压/电流/内阻/温度数据。
- **DS18B20**：PA3 (DQ)，30s 测量一次温度。
- **M_S (PA4)**：主从机检测引脚。开机时配置为内部上拉输入，检测电平：高=主机，低=从机。检测后切换为输入以省电。
- **自定义 UART 协议**：需设计地址分配、数据请求等协议。

**输出和指示：**
- 测量结果：电压、注入电流、内阻、温度。
- 从机向主机上报测量数据。

**时序和性能：**
- 系统时钟：64MHz (HSE 8MHz → PLL)。
- PWM：1kHz。
- ADC 采样率：10kHz，与电流相位同步。
- 内阻测量间隔：1 分钟。
- 温度测量间隔：30 秒。
- 全部非阻塞，基于状态机实现。

**测试和验收标准：**
- Keil UV4 编译通过（无错误）。
- 编译命令：`UV4.exe -j0 -b "MDK-ARM/battery_re.uvprojx" -o "MDK-ARM/build_log.txt"`

### Hardware Connection

### MCU / SoC
- **Part number:** STM32G030F6P6TR
- **Core / architecture:** Arm Cortex-M0+, 32-bit, up to 64 MHz
- **Package:** TSSOP-20 (6.4×4.4 mm)
- **Flash:** 32 KB, **SRAM:** 8 KB (with parity)
- **Datasheet:** DS12991 Rev 6

### Debug / Flash Interface
- **Protocol:** Serial Wire Debug (SWD)
- **Connector:** H5 (HDR-TH_4P-P2.54-V-M)
- **Pinout:** H5.1=3.3V, H5.2=ISOGND, H5.3=SWDIO (PF0), H5.4=SWCLK (PF1)
- **Required tools:** J-Link, ST-Link, pyOCD, or ULINK (Keil UL2CM3)

### Peripheral Wiring

| 信号 | MCU Pin | 目标器件 | 方向 | 备注 |
|------|---------|---------|------|------|
| UART1_TX | 20 (PB3) | CN4.3 → R11.1 | OUT | 级联通信主机端 TX |
| UART1_RX | 1 (PA10) | CN4.2 → R10.1 | IN | 级联通信主机端 RX |
| UART2_TX | 9 (PA1) | U5.6 (CA-IS3721) → CN3.2 | OUT | 级联通信从机端 TX（经隔离） |
| UART2_RX | 10 (PA2) | U5.7 (CA-IS3721) → CN3.3 | IN | 级联通信从机端 RX（经隔离） |
| DQ | 11 (PA3) | H6.2 (xh2.54-3P) + R6(4.7kΩ上拉) | I/O | DS18B20 温度传感器 |
| M_S | 12 (PA4) | R9(100kΩ上拉) | IN | 主从检测：高=主机, 低=从机 |
| VOLT_ADC | 8 (PA0) | 分压网络 (R4-1/R5-1) → 电池两端 | IN | 电池电压 ADC 采样 |
| CURRENT_ADC | 13 (PA5) | U11.1 (运放输出) | IN | 注入电流 ADC 采样 |
| RES_ADC | 14 (PA6) | U10.7 (运放输出) | IN | 采样电阻电压 ADC 采样 |
| TIM3_CH3 | 15 (PA7) | R21.1 → RC滤波 → OP1 | OUT | 1kHz PWM 方波输出，经 RC 生成正弦波 |
| NRST | 6 (NRST) | U6.1 (电容去耦) | IN | 外部复位 |
| SWDIO | 18 (PF0) | H5.3 | I/O | 调试接口 |
| SWCLK | 19 (PF1) | H5.4 | IN | 调试接口 |
| PA8 | 3 (PA8) | U5.4 (CA-IS3721) + CN3.4 | I/O | 隔离器通道 B 输出，接外部连接器 |
| PA9 | 2 (PA9) | U5.1 (CA-IS3721) + CN3.1 | I/O | 隔离器通道 A 输入，接外部连接器 |
| PB0 | 16 (PB0) | 未连接 | — | **未使用** |
| PB1 | 17 (PB1) | 未连接 | — | **未使用** |

**注：** TIM3_CH3 标签来自网表。根据 STM32G030F6P6 TSSOP20 引脚定义，PA7 的 AF 映射为 TIM3_CH2 而非 TIM3_CH3。[推断] 这可能是个网表标签错误，实际功能产生 1kHz PWM，无论用哪个通道均可实现。

### Power

| 电源轨 | 电压 | 来源 | 去向 |
|--------|------|------|------|
| +12V | 12V | CN1/CN2 外部输入 | 飞振控制器 U1-1 (VPS8701B) |
| 3.3V | 3.3V | U2-1 (XC6206P332MR, LDO) | MCU VDD, 隔离器 U5, 数字电路 |
| 3.3VA | 3.3V (模拟) | 经铁氧体磁珠从 3.3V 分离 | 运放 U9/U10/U11, 晶体管 Q1/Q3 |
| 5V | 5V | 飞振输出 (U1-1 + T1-1) | 整流二极管 D2-1/D3-1, LDO U2-1 输入 |
| 5VA | 5V (模拟) | 经 R2(10Ω) 从 5V 分离 | OP1 (LM258) 供电 |
| 1.65V | 1.65V | U1 (TLV431) 从 3.3V 分压 | 运放偏置，ADC 参考中点 |
| ISOGND | 0V | 隔离侧地 | 所有隔离侧电路地 |
| GND | 0V | 非隔离侧地 | 初级侧电路地 |

- **保护：** D1 (SMAJ15CA, TVS 15V) 跨接在 +12V 与 GND；F1-1 (0603L050YR PTC 自恢复保险) 在 RES_SENSOR- 路径上。
- **采样电阻：** R16 = 0.1Ω ±1% (0805)，连接 RES_SENSOR+ 和 RES_SENSOR-。

### Key Components

| 位号 | 型号 | 封装 | 功能 |
|------|------|------|------|
| U3-1 | STM32G030F6P6 | TSSOP-20 | 主控 MCU |
| U2-1 | XC6206P332MR | SOT-23-3 | 3.3V LDO 稳压器 |
| U1 | TLV431AIDBZR | SOT-23-3 | 1.65V 可调精密并联稳压器 |
| U1-1 | VPS8701B | SOT-23-6 | 飞振控制器（隔离电源） |
| T1-1 | VPT87DFB01B | 变压器 | 飞振变压器 |
| U5 | CA-IS3721LS | SOIC-8 | 双通道数字隔离器（隔离 UART2） |
| OP1 | LM258DT | SOIC-8 | 双通道运放（电流注入驱动） |
| U8, U9, U10, U11 | (未标注) | SOP-8 | 信号调理运放（电流/电压/电阻测量） |
| Q1~Q4 | SS8050 | SOT-23-3 | NPN 晶体管（开关/驱动） |
| D1-1 | SMAJ15CA | SMA | 15V TVS 保护 |
| D1 | (未标注) | SMB | 整流二极管 |
| D2-1, D3-1 | RB160M-30 | SOD-123 | 30V 肖特基二极管（次级整流） |
| R16 | 0.1Ω | 0805 | 电流采样电阻 |
| CN1, CN2 | HT396V-3.96-2P | 2P 接线端子 | 12V 电源输入 |
| CN3, CN4 | KF2EDGV-2.54-4P | 4P 接线端子 | 通信连接器 |
| H6 | xh2.54-3P | 3P 连接器 | DS18B20 传感器接口 |

### Uncertainties
1. **U8/U9/U10/U11 具体型号未知**：BOM 中 SOP-8 封装未标注型号。[推断] 根据连接关系判断为通用运放（如 LMV321 或 LM358 系列），但实际型号需确认。
2. **TIM3_CH3 vs TIM3_CH2**：网表将 PA7 输出标为 TIM3_CH3，但 STM32G030 数据手册中 PA7 AF 为 TIM3_CH2。[推断] 需要使用 TIM3_CH2 输出 PWM，或确认是否有内部重映射。
3. **ADC 通道号**：具体 ADC 输入通道号需根据 STM32G030F6P6 数据手册确认（PA0/PA5/PA6 分别映射到 ADC_IN1/ADC_IN6/ADC_IN7 或其他通道）。
4. **U3 (C0603 电容)** 和 **U4/U6/U7**：网表中列为 C0603 封装电容（U 位号），可能是去耦电容或未组装位。

### Build, Flash, And Run Notes

- **Build system:** Keil MDK-ARM (uVision), ArmClang V6.19
- **IDE/工具链路径:** `C:\Keil_v5\UV4\UV4.exe`
- **Build command (batch):**
  ```
  UV4.exe -j0 -b "MDK-ARM/battery_re.uvprojx" -o "MDK-ARM/build_log.txt"
  ```
  - `-j0`: 禁止弹窗
  - `-b`: 增量编译
  - 退出码: 0=成功, 1=有 warning 无 error, 2-20=编译 error, 21+=fatal
- **Define macros (uvprojx):** `USE_HAL_DRIVER,STM32G030xx`
- **Include paths:**
  - `../Core/Inc`
  - `../Drivers/STM32G0xx_HAL_Driver/Inc`
  - `../Drivers/STM32G0xx_HAL_Driver/Inc/Legacy`
  - `../Drivers/CMSIS/Device/ST/STM32G0xx/Include`
  - `../Drivers/CMSIS/Include`
  - `..\Drivers\CMSIS\DSP\Include`
- **Linker:** 默认 ArmClang 链接器，无分散加载文件指定，使用默认 `battery_re.sct`
- **Output:** `battery_re/battery_re.axf` (ELF)，同时生成 `battery_re/battery_re.hex` (Intel HEX)
- **Memory map:**
  - Flash: 0x08000000, 64 KB (实际器件 32 KB)
  - RAM: 0x20000000, 8 KB
  - Stack: 0x400 bytes, Heap: 0x200 bytes
- **Flash command:** `pyocd flash -t stm32f103c8 build/firmware.elf` (来自 hardware_config — 但目标 MCU 是 STM32G030F6P6，此命令需验证。实际应使用 STM32G030 目标)
- **Serial observation:** COM3 / 115200 / 8N1

### Constraints And Risks

1. **USART1 引脚分配非常规**：RX 在 PA10 (pin 1)，TX 在 PB3 (pin 20)。需确认 USART1 的 AF 重映射配置正确。
2. **GPIO_AF2_TIM3 编译错误**：此前构建失败是因为 `stm32g0xx_hal_msp.c` 中使用了错误的宏名。STM32G0 系列中 Timer 的 AF 宏定义方式与其他系列不同，需查阅 `stm32g0xx_hal_gpio.h` 确认正确宏。
3. **PWM 引脚功能确认**：PA7 的 AF 为 TIM3_CH2 (AF2)。如果设计要求 TIM3_CH3，可能需要改用 PB0 (pin 16) 或接受 TIM3_CH2。
4. **DS18B20 时序**：DS18B20 需要严格的 1-Wire 时序。STM32G030F6P6 无硬件 1-Wire 控制器，需用 GPIO 位带操作模拟或使用 USART 的 1-Wire 模式。
5. **ADC 采样同步**：要求 10kHz ADC 采样与电流相位同步。可能需使用 TIM3 触发 ADC 注入组或规则组转换。
6. **Flash 容量**：仅 32KB Flash，含 HAL 库后可用空间有限。需注意代码大小优化。
7. **硬件验证限制**：无实际硬件可测试，所有硬件连接基于网表和 BOM 推断。
8. **U8/U9/U10/U11 型号未知**：无数据手册，无法确认其输入/输出范围和特性。

### Confidence Assessment

| Section | Confidence | Reason |
|---------|-----------|--------|
| Goal | High | 用户需求明确，文件描述清晰。 |
| Task Requirements | High | user_req.txt 提供完整的需求列表。 |
| Hardware Connection | Medium | 网表提供了完整连接，但部分 IC 型号未知(U8~U11)，TIM3 通道号可能有误差。电源树清晰。 |
| Build & Flash | High | Keil 工程配置完整且已有成功构建日志。Flash 命令需根据实际 MCU 修正。 |
| Constraints & Risks | Medium | 主要风险是 Flash 容量限制、未知运放型号、无硬件验证条件。 |
```