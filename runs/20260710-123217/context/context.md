Now I have sufficient information. Writing the comprehensive context.md.

---

# Build Context

### Goal

完成STM32G030F6P6（TSSOP-20）为核心的电池内阻测量系统固件。MCU产生1kHz/50%占空比方波，经RC滤波->跟随器->运放形成交流恒流注入电池，同步采样电池两端电压（10kHz与电流相位同步），计算内阻。通过DS18B20每30秒测一次温度。多电池手拉手UART级联：UART1为主机发往下一从机，UART2为从机接收上一主机指令。通过pin12（M_S）高低电平在开机时判断主/从角色。整体非阻塞状态机架构，含异常数据识别算法。

### Source Materials

### Directory Overview

| Directory | Summary |
|-----------|---------|
| `battery_re/` | Keil MDK-ARM工程根目录，包含Core（应用代码）、Drivers（HAL/CMSIS）、MDK-ARM（项目配置/启动文件/构建产物） |
| `battery_re/Core/Inc/` | 应用头文件：`stm32g0xx_hal_conf.h`（HAL模块选择）、`stm32g0xx_it.h` |
| `battery_re/Core/Src/` | 应用源文件：`stm32g0xx_it.c`（中断服务）、`system_stm32g0xx.c`（系统时钟初始化） |
| `battery_re/Drivers/STM32G0xx_HAL_Driver/` | ST官方STM32G0 HAL驱动库（Inc + Src），已启用ADC、TIM、UART、DMA、GPIO、EXTI、IWDG等模块 |
| `battery_re/Drivers/CMSIS/` | CMSIS核心及DSP库 |
| `battery_re/MDK-ARM/` | Keil项目文件（`.uvprojx`）、启动代码、链接脚本、构建产物（`.axf` `.hex` `.map`） |
| `.document-reader/` | 硬件文档解析结果：DS12991（MCU数据手册）、BOM、netlist（网表） |
| `.understand-anything/` | 中间文件（临时） |

### Key Files Inspected

- `user_req.txt` — 用户需求文档（核心功能、引脚分配、工程要求）
- `Netlist_Schematic1_2026-05-25.tel` — 电路网表（原始格式），包含所有网络连接
- `.document-reader/netlist/document.md` — 网表Markdown版本
- `.document-reader/BOM/document.md` — BOM清单Markdown版本
- `.document-reader/DS12991/chunks/chunk_0034.md` — DS12991数据手册第4节引脚图（TSSOP20）
- `battery_re/Core/Src/stm32g0xx_it.c` — 当前中断服务实现（弱符号桩函数为主）
- `battery_re/Core/Src/system_stm32g0xx.c` — 系统时钟初始化：HSE 8MHz -> PLL -> 64MHz SysClk
- `battery_re/Core/Inc/stm32g0xx_hal_conf.h` — HAL模块选择配置
- `battery_re/MDK-ARM/battery_re.uvprojx` — Keil项目配置（设备、编译选项、源文件组）
- `battery_re/MDK-ARM/startup_stm32g030xx.s` — 启动代码/向量表
- `battery_re/MDK-ARM/battery_re.sct` — 分散加载文件（IROM 0x08000000 64KB, IRAM 0x20000000 8KB）
- `battery_re/MDK-ARM/build_log.txt` — 最近一次成功构建日志（0 Error, 0 Warning）

### Task Requirements

**Functional behavior:**
- PWM产生1kHz/50%占空比方波 -> RC滤波 -> 正弦波 -> 跟随器 -> 恒流注入电池（交流）
- 10kHz同步采样电池两端电压（与注入电流相位同步），计算内阻
- 每1分钟测量一次内阻（用户需求第8点）
- DS18B20（DQ线）每30秒测量温度
- 多电池UART级联：UART1作为主机发往下一从机，UART2作为从机接收上一主机指令
- pin12（M_S）开机时判断主/从：内部上拉 -> 若为低电平则为主机，否则为从机；判断后改为输入
- 主机给从机分配地址，定时读取从机数据（电压、内阻、温度等）
- 整体非阻塞状态机实现
- 异常数据识别算法（抗充电/放电干扰）
- 相位校准 + 多点电阻校准

**Interfaces and protocols:**
- UART1：主机 <- (TX/RX) -> 下一电池从机
- UART2：从机 <- (TX/RX) -> 上一电池主机
- 自定义UART级联通讯协议（地址分配、数据读取）
- DS18B20单总线协议（30s一次）

**Outputs and indicators:**
- 无显式输出设备（可能是通过UART级联上报数据）

**Timing and performance:**
- PWM 1kHz, 50% duty
- ADC采样 10kHz（同步）
- 内阻测量周期 1分钟
- 温度测量周期 30秒
- 系统时钟 64MHz

**Tests and acceptance criteria:**
- Keil编译通过（0 Error, 0 Warning）
- 所有代码需添加到`.uvprojx`工程中

### Hardware Connection

### MCU / SoC

- **Part number:** STM32G030F6P6TR
- **Core / architecture:** ARM Cortex-M0+, 64MHz max
- **Package:** TSSOP-20 (6.5×4.4mm, 0.65mm pitch)
- **Flash:** 32KB (STM32G030x6)
- **SRAM:** 8KB
- **Datasheet:** DS12991 Rev 6

### Debug / Flash Interface

- **Protocol:** Serial Wire Debug (SWD)
- **Connector / pinout:** H5（4-pin header 2.54mm）
  - H5.1 = 3.3V
  - H5.2 = ISOGND
  - H5.3 = SWDIO (PA13) -> U3-1.18
  - H5.4 = SWCLK (PA14) -> U3-1.19
- **Required tools:** JLink / ST-Link / Keil ULINK2 via SWD

### Peripheral Wiring

| Signal | MCU Pin (TSSOP20) | Target Device / Module | Direction | Notes |
|--------|-------------------|----------------------|-----------|-------|
| UART1_RX | Pin 1 (PB7, AF0) | CN4.2 (xh2.54-4P) via R10(10Ω) | Input | 级联接口主机RX |
| UART1_TX | Pin 20 (PB6, AF0) | CN4.3 (xh2.54-4P) via R11(10Ω) | Output | 级联接口主机TX |
| UART2_RX | Pin 10 (PA3, AF1) | CN3.1 (xh2.54-4P) via R7(10Ω) -> U5(CA-IS3721) | Input | 级联接口从机RX（经隔离） |
| UART2_TX | Pin 9 (PA2, AF1) | CN3.4 (xh2.54-4P) via R8(10Ω) -> U5(CA-IS3721) | Output | 级联接口从机TX（经隔离） |
| DQ | Pin 11 (PA4) | H6.2 (xh2.54-3P) via R6(4.7kΩ) | Bidir | DS18B20数据线（上拉至3.3V） |
| M_S | Pin 12 (PA5) | R9(100kΩ)上拉至3.3V | Input | 主从检测：低=主机，高=从机 |
| TIM3_CH3 | Pin 15 (PB0, AF1) | R21(100kΩ) -> RC滤波网络 | Output | 1kHz PWM方波输出 |
| CURRENT_ADC | Pin 13 (PA6, ADC_IN6) | U10(运放SOP-8)输出 -> R52(100kΩ) | Input | 注入电流采样 |
| RES_ADC | Pin 14 (PA7, ADC_IN7) | U10.7 -> R38(10kΩ)/C24(1nF) | Input | 电池电阻端电压采样 |
| VOLT_ADC | Pin 8 (PA1, ADC_IN1) | U3-1.8 (分压网络) | Input | 电池电压ADC |
| NRST | Pin 6 | U6(C0603 100nF) 到地 | Input | 外部复位（连接到电容） |
| VDD/VDDA | Pin 4 | 3.3V网络 | Power | MCU主电源 |
| VSS/VSSA | Pin 5 | ISOGND网络 | Power | MCU地（隔离地） |
| Pin 7 (PA0) | Pin 7 | 未连接（根据网表） | - | 空闲GPIO |
| SWCLK | Pin 19 (PA14) | H5.4 | Input | 调试时钟 |
| SWDIO | Pin 18 (PA13) | H5.3 | Bidir | 调试数据 |

**UART隔离：** U5 = CA-IS3721LS（SOIC-8，川土微电子），用于UART2的隔离通信（隔离地ISOGND与GND分离）。

**CN3/CN4连接器：**
- CN3（xh2.54-4P）：UART2隔离接口（从机侧）
  - CN3.1: UART2_RX (经U5隔离)
  - CN3.2: U5.2
  - CN3.3: U5.3
  - CN3.4: UART2_TX (经U5隔离)
- CN4（xh2.54-4P）：UART1非隔离接口（主机侧）
  - CN4.1: 3.3V
  - CN4.2: UART1_RX
  - CN4.3: UART1_TX
  - CN4.4: ISOGND

**H6（xh2.54-3P）：**
- H6.1: 3.3V
- H6.2: DQ (DS18B20)
- H6.3: ISOGND

**H1-H4（电池端子）：** H1 = RES_SENSOR-, H2 = ISOGND, H3 = 3.3V, H4 = 3.3V

**交流恒流生成链路：**
```
TIM3_CH3(PB0) -> R21(100k) -> C7(1nF) -> R20(100k) -> C6(1nF) -> R19(100k) -> C5(1nF) -> R18(100k) -> C4(1nF) -> OP1(LM258)跟随器 -> U9/U10(运放)恒流 -> 电池
```
三级RC低通滤波将1kHz方波转换为正弦波。

**采样电阻：** R16 = 0.1Ω（0805封装），串联在电池回路中用于电流检测。

### Power

- **Supply voltage:** 12V输入（CN1/CN2）
- **Regulator / LDO:**
  - U2-1 = XC6206P332MR-G（SOT-23-3, TOREX）：5V -> 3.3V稳压
  - U1-1 = VPS8701B（SOT-23-6, VPSC）：隔离电源模块（配合T1变压器）
  - U1 = TLV431AIDBZR（SOT-23-3, TI）：1.65V参考电压生成
- **Power rails:**
  - 12V: 从CN1/CN2输入
  - 5V: 经D2-1/D3-1(RB160M-30)降压
  - 3.3V: XC6206从5V稳压（数字供电）
  - 3.3VA: 模拟供电（经R1(10Ω)/C2-2隔离）
  - 1.65V: TLV431生成（用于运放偏置）
  - ISOGND: 隔离地
- **Power sequencing notes:** 无特殊时序要求

### Uncertainties

- **Pin 2 (PB9/PC14-OSC32_IN) 和 Pin 3 (PB0/PC15-OSC32_OUT)** 在网表中未显式连接。如果使用外部32kHz晶振（LSE），则用于RTC。当前未看到LSE晶振在BOM中。
- **Pin 16/17 (PA9/PA10)** 在网表中无显式连接，可能备用。
- **UART通讯速率** 未在需求中指定。[推断] 常见9600或115200 bps。
- **CN1/CN2** 为2P-3.96mm接线端子，标记+12V/GND，为系统电源输入。
- **F1-1 (0603L050YR)** 为自恢复保险丝（0.5A），串联在RES_SENSOR+路径上。

### Build, Flash, And Run Notes

- **Build system:** Keil MDK-ARM v5 (uVision)
- **Toolchain:** ArmClang V6.19 (ARM-ADS)
- **Device:** STM32G030F6Px
- **Pack:** Keil.STM32G0xx_DFP.1.4.0

**Build command:**
```powershell
C:\Keil_v5\UV4\UV4.exe -j0 -b "MDK-ARM/battery_re.uvprojx" -o "MDK-ARM/build_log.txt"
```
- `-j0`：抑制状态弹窗
- `-b`：batch build（增量编译）
- 退出码：0成功, 1有警告, 2-20编译错误, 21+致命错误

**Flash command:**
通过Keil IDE的Download按钮（使用UL2CM3驱动，STM32G0xx_32.FLM算法），或使用ST-Link Utility / JFlash独立烧录。

**Preprocessor defines:** `USE_HAL_DRIVER,STM32G030xx`

**Include paths:**
```
../Core/Inc
../Drivers/STM32G0xx_HAL_Driver/Inc
../Drivers/STM32G0xx_HAL_Driver/Inc/Legacy
../Drivers/CMSIS/Device/ST/STM32G0xx/Include
../Drivers/CMSIS/Include
..\Drivers\CMSIS\DSP\Include
```

**Output artifacts:**
- `battery_re/battery_re.axf` (ELF with debug info)
- `battery_re/battery_re.hex` (Intel HEX)
- Memory: IROM 0x08000000 (64KB), IRAM 0x20000000 (8KB)

**Serial / debug observation:**
- 主机UART1（PB6/PB7）用于级联通讯
- 从机UART2（PA2/PA3，经CA-IS3721隔离）用于级联通讯
- [推断] 调试串口速率待定（可能9600或115200）

**Working directory:** `battery_re/`（在`battery_re/MDK-ARM/battery_re.uvprojx`中配置Output Directory为`battery_re\`）

### Constraints And Risks

- **Missing information:** UART通讯波特率未指定，需在协议设计中确定
- **Unclear hardware details:** Pin 2/3/7/16/17用途不明确（从网表看未连接外部设备）
- **Uncertain build or flash commands:** 用户指定Keil UV4命令行编译方式，无独立烧录脚本
- **Incomplete acceptance criteria:** 用户需求中未指定验收测试用例
- **Truncated or unreadable files:** DS12991数据手册PDF解析为Markdown时表格格式混乱，引脚图依赖ASCII art，TSSOP20引脚映射通过交叉比对网表和datasheet图推导
- **Real-hardware verification risks:** 多电池级联需要多块硬件板才能完整测试主从通讯
- **DS18B20** DQ线同时连接H6.2（外接传感器）和R6上拉至3.3V，信号完整性依赖物理接线
- **恒流回路** 的相位校准和多点电阻校准需要实际硬件和参考电阻进行标定

### Confidence Assessment

| Section | Confidence | Reason |
|---------|-----------|--------|
| Goal | High | 用户需求明确描述了电池内阻测量系统全部功能 |
| Task Requirements | High | 19条需求项详细描述了功能、引脚、通讯、时序、架构 |
| Hardware Connection | Medium-High | 网表完整，TSSOP20引脚通过交叉比对datasheet和网表确定；引脚15(TIM3_CH3)推断为PB0（AF1）匹配；少数引脚用途不明 |
| Build & Flash | High | `.uvprojx`配置完整，有成功构建日志（0 Error），编译命令明确 |
| Constraints & Risks | Medium | 少数硬件细节不明确，UART波特率未指定，协议待设计，缺少验收测试用例 |