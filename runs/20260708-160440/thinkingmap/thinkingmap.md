好的，首席架构师。收到上游的 `G_CONTEXT_BUILD` 上下文。现在，我将以12维度深度扫描框架，为你构建一份高信息密度的项目上下文引擎（Thinking Map）。这不仅仅是需求文档，这是整个AI Agent研发管线的唯一真理源。

---

```json
{
  "project_summary": "基于STM32G030F6P6的交流注入法单电池内阻测量节点，通过UART级联构成主从多节点网络，实现电池组内每个电池的定时内阻与温度测量，所有数据汇聚至主节点上报。",
  "system_archetype": "rtos_bare_metal_state_machine",
  "resource_constraints": {
    "mcu": "STM32G030F6P6 (ARM Cortex-M0+, 64MHz, TSSOP-20)",
    "flash": "64 KB (0x08000000 - 0x0800FFFF)",
    "sram": "8 KB (0x20000000 - 0x20001FFF)",
    "stack_size": "1 KB (由启动文件指定)",
    "heap_size": "512 Bytes (由启动文件指定)",
    "key_peripherals": {
      "adc": "1个12位ADC (最多19通道), 1Msps",
      "timers": "TIM1(16-bit), TIM3(16-bit), TIM14(16-bit)",
      "usart": "2个USART (USART1, USART2)",
      "other": "DMA (3通道), IWDG, 7个GPIO (外部中断)"
    }
  },
  "persona_pool": [
    {
      "role_name": "BSP/底层驱动专家",
      "core_focus": "时钟树配置、GPIO引脚复用与初始化、中断优先级与嵌套管理、外设 (ADC, TIM, UART, DMA)的精确配置, 内存布局(LD文件)裁剪。",
      "review_lens": "审查应用层代码时，最关心：该算法/逻辑是否意外修改了外设寄存器？是否在ISR中执行了阻塞操作？栈使用是否接近1KB极限？全局变量是否导致RAM溢出？"
    },
    {
      "role_name": "应用层/状态机专家",
      "core_focus": "全局状态机的设计（状态、事件、跃迁的完备性）、非阻塞设计（时间片轮转或事件驱动）、模块间解耦（消息队列或函数指针回调）、定时服务（Systick或TIM14）的实现。",
      "review_lens": "审查底层驱动时，最关心：驱动接口是否设计成了阻塞模式？`HAL_Delay()` 是否被使用？回调函数是否在中断上下文中调用了可能阻塞的模块？"
    },
    {
      "role_name": "算法/信号处理专家",
      "core_focus": "交流注入法的采样同步方案的精度、1kHz基波提取（Goertzel算法或整周期DFT）、RMS计算、相位差校准算法、异常数据识别算法的有效性，及在M0+上的资源消耗和WCET。",
      "review_lens": "审查系统整体时，最关心：ADC采样与PWM的硬件同步机制是否可靠？`__IQ`或`float`运算是否符合时序要求？数组大小是否满足整周期采样？抗干扰算法是否会产生误判？"
    },
    {
      "role_name": "通讯协议专家",
      "core_focus": "UART级联协议的设计（帧格式、寻址、校验、重传机制）、主从机角色识别的鲁棒性、半双工总线仲裁、缓冲区溢出防护。",
      "review_lens": "审查状态机或驱动时，最关心：UART中断接收缓冲区是否足够大（如2倍最大帧长）？协议解析是否过于复杂，导致状态机长时间占用CPU？是否考虑了总线空闲时的超时处理？"
    },
    {
      "role_name": "硬件/系统集成专家",
      "core_focus": "模拟电路（RC滤波、恒流源、差分放大）与数字电路的时序匹配、电源完整性（尤其模拟3.3VA）、隔离器(CA-IS3721LS)的通信延迟、PCB走线（模拟信号与数字信号的隔离）。",
      "review_lens": "审查软件时，最关心：ADC采样率(10kHz)与PWM频率(1kHz)的同步是否受隔离器延迟影响？PWM输出经RC滤波后的相位延迟是否在可校准范围内？Vref (1.65V)的精度是否满足内阻计算要求？"
    }
  ],
  "angle_sweep": {
    "1. 技术栈与关键路径": {
      "mcu_architecture": "ARM Cortex-M0+ (冯诺依曼架构, 单周期乘法, 无MPU/FPU)",
      "toolchain": "ArmClang V6.19 (Keil MDK)",
      "hal": "STM32G0xx_HAL_Driver (HAL库与LL库混合)",
      "dsp_lib": "CMSIS-DSP (arm_cortexM0l_math.lib, 主要用Q15或Q31数学函数)",
      "critical_timing_path": "ADC注入组采样触发链路: TIM1_TRGO (更新事件) -> ADC注入组启动 -> 注入序列结束 (JEOC) -> DMA请求 -> 数据搬运至内存。整个链路必须精确控制在100us (10kHz)内，且受DMA响应延迟和总线仲裁影响。",
      "core_algorithm": [
        "整周期10点DFT (1kHz基波提取)",
        "RLS (递推最小二乘) 或 NLLS (非线性最小二乘) 用于相位和幅度估算",
        "RC 网络补偿滤波器 (基于`1/(1 + sRC)`)",
        "基于统计阈值(3-sigma或MAD)的异常值剔除算法"
      ]
    },
    "2. 业务逻辑与状态流": {
      "core_business_logic": "实现电池内阻与温度的循环测量与上报，提供可寻址的电池单元监控数据。",
      "global_state_machine": {
        "states": [
          {"name": "INIT", "desc": "系统初始化，时钟、外设、参数配置"},
          {"name": "IDLE", "desc": "等待定时触发或主机命令"},
          {"name": "MEASURE_START", "desc": "启动PWM输出，建立稳定的交流电流场"},
          {"name": "ACQ_SYNC", "desc": "ADC同步采样窗口（1个交流周期，10个点）"},
          {"name": "PROCESS", "desc": "数字滤波、相位补偿、RMS计算、异常检测"},
          {"name": "STORE_AND_REPORT", "desc": "存储结果至EE (如有)，等待主机轮询或主动上报"},
          {"name": "SLEEP", "desc": "低功耗模式，唤醒源为RTC/TIM或主机指令"},
          {"name": "ERROR_HANDLER", "desc": "故障诊断与恢复（如传感器断线、通信超时）"}
        ],
        "transition_events": [
          "EVT_INIT_DONE", "EVT_TIMER_EXPIRED(60s)", "EVT_DS18B20_DONE(30s)",
          "EVT_MEAS_CMD_FROM_HOST", "EVT_ADC_DMA_HALF_CMPLT", "EVT_ADC_DMA_CMPLT",
          "EVT_PROC_DONE", "EVT_COMMS_TIMEOUT", "EVT_ERROR"
        ]
      },
      "core_dataflow": "AC Current Inject (TIM3_PWM -> RC -> V-to-I) -> Battery -> Voltage Sense (PA1/VOLT_ADC) & Current Sense (PA6/CURRENT_ADC) -> 10kHz ADC (Inject Group) -> DMA (Circular Buffer) -> Offset/Scale Correction -> Goertzel/DFT -> Phase Comp -> R = V/I -> Abnormal Check -> Temp (DS18B20) -> UART2 (Slave) -> UART1 (Master) -> Next Node"
    },
    "3. 虚拟专家角色池": "(已在上方 `persona_pool` 字段中定义)",
    "4. 风险与 FMEA 分析": {
      "risk_1": {
        "failure_mode": "栈溢出",
        "effects": "程序跑飞 (HardFault)、系统崩溃",
        "cause": "8KB RAM中栈空间仅1KB，递归调用或深层嵌套函数在中断过程中导致栈溢出。",
        "mitigation": "静态分析(使用 `-Wstack-usage=` 或编译报告)；中断ISR内只设置标志位，不调用复杂函数；使用MSP和PSP (非M3, M0+只有MSP)进行任务堆栈隔离；考虑在启动文件后增加栈保护区(Guardian page)检测。"
      },
      "risk_2": {
        "failure_mode": "ADC采样与PWM不同步",
        "effects": "相位测量不准，内阻计算值抖动或完全错误",
        "cause": "TIM1_TRGO触发ADC注入组的时序配置错误，或DMA响应延迟导致采样点相位漂移。",
        "mitigation": "使用注入组(Injected Group)实现硬件触发，优先级最高；在DMA传输完成中断中检查采样点数是否为完整周期(10个点)；软件上加入基于过零点的相位锁定环(PLL)算法。"
      },
      "risk_3": {
        "failure_mode": "外部强干扰（充电/逆变器）导致ADC读数和通信异常",
        "effects": "测量偏差、误触发看门狗复位、UART数据帧错误",
        "cause": "电池端逆变器或充电机产生的高频共模/差模噪声，耦合至模拟信号路径和隔离通信链路。",
        "mitigation": "硬件：加强RC滤波(更高阶)；软件：ADC输入增加数字陷波滤波器(Notch filter, 如500Hz-2kHz)；UART：开启奇偶校验，CRC16校验，并实施重试机制；增加IWDG窗口模式，防止在错误处理循环中溢出。"
      }
    },
    "5. 依赖与前置条件": {
      "hardware_deps": [
        "BOM清单中的XC6206P332MR-G (LDO)必须能提供稳定3.3V/200mA",
        "CA-IS3721LS隔离器需确认其最高通信速率(可能限制UART波特率)",
        "VPS8701B隔离DC-DC的纹波需<50mV，否则影响ADC基准",
        "TSSOP-20焊接质量是关键，引脚间距0.65mm易桥接"
      ],
      "software_deps": [
        "STM32CubeG0 v1.6.0 及以上版本的HAL驱动库",
        "CMSIS-DSP Arm Cortex-M0 Library"
      ],
      "environment_deps": [
        "Keil MDK V5.38 或更高版本 (支持ArmClang V6.19 C17标准)",
        "JTAG/SWD调试器 (ST-Link或J-Link)"
      ]
    },
    "6. 接口与集成契约": {
      "physical_interfaces": {
        "uart1_master": {"baud": "115200", "parity": "even", "stop_bits": "1", "protocol": "custom", "level": "3.3V CMOS"},
        "uart2_slave": {"baud": "115200", "parity": "even", "stop_bits": "1", "protocol": "custom", "level": "3.3V CMOS"},
        "ds18b20": {"protocol": "1-Wire", "pullup": "4.7kΩ to 3.3V", "parasite_power": "不支持"},
        "adc_inputs": {"voltage_input": "PA1(AIN1), 0-3.3V", "current_input": "PA6(AIN6), 0-3.3V", "reference": "VDDA=3.3V, VSSA=ISOGND"},
        "pwm_output": {"pin": "PB0(TIM3_CH3)", "freq": "1kHz", "duty": "50%", "after_rc": "approx 1.6kHz LPF"}
      },
      "software_internal_interfaces": {
        "inter_module_comm": "全局结构体+原子操作共享变量 (如 `volatile BatteryData_t`)，ISR与主循环间通过状态标志传递",
        "callback_contract": "HAL库的回调函数 (如 `HAL_ADC_ConvCpltCallback`) 必须在中断上下文中立即执行，禁止阻塞或耗时操作，仅设置标志位或启动DMA传输",
        "buffer_management": "ADC使用2个512字节环形缓冲区（双缓冲模式）；UART使用512字节Rx环形缓冲区 + 128字节Tx缓冲区"
      },
      "external_communication_protocol": {
        "frame_format": "帧头(0xAA 0x55) + 从机地址(1字节) + 命令码(1字节) + 数据长度(1字节) + 数据体(N字节) + CRC16(2字节)",
        "crc16_algorithm": "Modbus RTU (CRC-16-IBM) 或 CRC-CCITT",
        "addressing": "主机在上电后或通过特定命令分配地址 (0x01-0xFE)；0xFF为广播地址",
        "retransmission": "主机发送命令后启动100ms超时定时器；若未收到回复，主机重发命令，最多重试2次。重试失败则标记该节点离线。"
      }
    },
    "7. 深度测试与验证策略": {
      "sil": "在PC上用MinGW或Visual Studio环境，创建一个 `test_harness`。模拟ADC值和温度传感器数据，验证RMS计算、相位校准、内阻算法和异常检测逻辑的正确性。所有算法函数必须是纯C实现，无硬件依赖。",
      "hil": {
        "instruments": [
          "信号发生器(Sine wave output, 1kHz, 0-3.3V)注入至VOLT_ADC和CURRENT_ADC",
          "电子负载(Constant Current mode)模拟电池伏安特性",
          "精密电阻箱(0.1%精度)用于多点校准",
          "四通道示波器(200MHz BW) 监测：PWM输出、RC后波形、ADC采样点、隔离器输出",
          "逻辑分析仪(16通道) 分析UART帧及DS18B20时序"
        ],
        "test_cases": [
          "以1mΩ步进，从0.5mΩ到100mΩ测试内阻线性度",
          "在Vbat输入端叠加50Hz/2Vpp交流干扰，测试异常检测算法",
          "断开DS18B20，观察系统是否切换到错误处理状态并报错"
        ]
      },
      "timing_physical_validation": {
        "tick_to_tick": "示波器测量PWM上升沿到ADC采样点(JEOC)的延迟，验证硬件同步链路是否在1us以内",
        "isr_wcet": "使用逻辑分析仪捕获`TIM1_TRIG`中断 (由ADC提供) 和`ADC_JEOC_IRQ`中断，测量ISR执行时间。在`-O0` (默认) 和 `-O3` 下分别验证，确保不超过200个CPU时钟周期(3.125us)",
        "dma_completion": "使用示波器测量DMA传输完成中断响应的抖动，确认其不影响10kHz采样窗口闭合。"
      },
      "fault_injection": {
        "vsens_disconnect": "断开VOLT_ADC引脚的飞线，观察ADC值是否超出阈值(>3.3V)，系统是否识别为故障并保持在IDLE状态",
        "comm_bus_storm": "连续向从机发送错误CRC帧，观察协议解析器的缓冲区是否会溢出或进入死循环。使用看门狗确保能恢复。",
        "power_glitch": "用电源分析仪产生5%-10%的瞬时电压跌落(Brown-out)，验证MCU的BOR (Power-on Reset) 阈值设置是否正确，复位后状态机是否可靠进入INIT模式。"
      },
      "metrology": {
        "calibration_procedure": "在装配工序中，使用上位机发送`CAL_CMD`。主机锁定后，依次接入N个精密电阻 (如1mΩ, 10mΩ, 50mΩ, 100mΩ)，上位机记录ADC读数并拟合两点/多点校准曲线 (线性回归)。校准参数写入Flash (UPage) 或通过UART指令下发到每个节点。",
        "validation_criteria": "线性度 ≤ 1% FS，重复性 ≤ 0.5% FS (在10次测量后)，温漂 ≤ 100 ppm/°C (在-20°C到60°C范围内测试)。"
      }
    },
    "8. 性能、资源与规模": {
      "resource_budget": {
        "flash": {
          "total_available": "64 KB",
          "reserved_for_isr_vector": "~256 B",
          "hal_drivers_estimate": "~35 KB",
          "cmsis_math": "~5 KB",
          "application_code": "~18 KB (用于状态机、协议、算法)",
          "calibration_data_reserved": "~1 KB (1 Page)",
          "total_estimated": "~59 KB"
        },
        "ram": {
          "total_available": "8 KB",
          "bss_data_global_vars": "~2 KB",
          "adc_dma_buffers": "2 * 256 Bytes = 512 B",
          "uart_rx_buffers": "2 * 512 Bytes = 1024 B",
          "uart_tx_buffers": "2 * 128 Bytes = 256 B",
          "stack": "1 KB (startup) + 256 B (ISR stack)",
          "heap": "512 B",
          "total_estimated": "~7.6 KB"
        }
      },
      "wcet_analysis": {
        "adc_isr": "~2.5 us (DMA完成标志检查 + 循环计数)",
        "uart_isr": "~5 us (接收一个字节并写入环形缓冲区)",
        "data_processing_task": "~10 ms (10点DFT + 内阻计算 + 异常检测, 取决于Q15/Q31优化)",
        "main_loop_iteration": "~10 ms (包含一次完整的测量、处理和上报流程)"
      },
      "bottleneck": "当级联节点数 > 16 时，UART总线轮询周期(每个节点约5ms) 将超过1分钟测量间隔，导致数据在主机侧拥塞。方案：增加主机缓存或使用多点下拉模式 (Multidrop RS-485)。"
    },
    "9. 安全与鲁棒性": {
      "physical_safety": [
        "输入12V电源有SMAJ15CA TVS管防浪涌",
        "电池端通过隔离DC-DC (VPS8701B) 和数字隔离器 (CA-IS3721LS) 实现电气隔离",
        "MCU供电由XC6206P332MR-G提供，内置过流/热关断保护"
      ],
      "software_robustness": [
        "所有UART数据处理函数使用安全宏 `(data_len > sizeof(buffer))` 检查，防止溢出",
        "通信协议帧解析使用状态机，防止错误帧导致解析器跑飞",
        "IWDG窗口喂狗：必须在 `PROCESS` 状态结束前或IDLE状态的循环内喂狗，防止在异常数据处理循环中死锁",
        "ADC采样值采用中值滤波(Order 3)先进行平滑，再输入异常检测器"
      ],
      "security_considerations": [
        "由于是在隔离边界内的私有协议(LAN)，攻击面较小。但仍需注意：UART广播帧可能导致地址冲突。",
        "固件可通过在Flash设置读保护(RDP Level 1)防止通过SWD接口读取。"
      ]
    },
    "10. 可维护性与演进": {
      "modular_boundaries": {
        "driver_layer": "独立文件: `adc_drv.c/h`, `tim_drv.c/h`, `uart_drv.c/h`, `ds18b20_drv.c/h`, `gpio_drv.c/h`",
        "middleware_layer": "独立文件: `ring_buffer.c/h`, `crc16.c/h`, `serial_protocol.c/h`",
        "application_layer": "核心文件: `main.c`, `state_machine.c/h`, `measurement_engine.c/h`, `abnormal_detector.c/h`, `calibration.c/h`"
      },
      "blackbox_mechanism": "将最后8次测量的完整数据(含时间戳)和最后3个错误码，存储到MCU的最后一个User Page (0x0800FC00) 中，使用双缓冲策略防止写入过程中掉电导致数据损坏。仅通过UART特定命令读取。",
      "ota_upgrade": "不支持。但可通过UART串口命令进行固件升级 (需bootloader支持)。现场参数校准通过UART指令完成。"
    },
    "11. 用户体验与反馈": {
      "headless_system_feedback": {
        "led": "无。可通过SWD接口上的`nRST`和`SWO`引脚复用为GPIO驱动外部LED（如果有）",
        "buzzer": "无。",
        "uart_cli": "定义简短的ASCII指令集（字节命令，非ASCII字符串）：`?`(查询状态), `S`(停止/开始测量), `C`(进入校准模式)。错误码以单字节发送，如`0xE1`(ADC over/underflow), `0xE2`(DS18B20 crc error), `0xE3`(UART timeout)。"
      },
      "production_tools": {
        "one_click_calibration": "工装夹具上电后，自动进入SELF_TEST模式，依次测试DS18B20、ADC通道、PWM输出。上位机监听UART输出，若收到错误码则触发NG信号。",
        "self_test_mode": "上电后按住某个IO (比如M_S引脚拉低后上电) 强制进入自检模式。系统会循环测量一个内部参考电阻，并输出ADC原始读数。"
      }
    },
    "12. 时间节奏与关键路径": {
      "parallel_strategy": {
        "phase_1 (3天)": "",
        "task": "在STM32G030 Nucleo-32开发板上验证核心算法：DMA+TIM1+ADC注入组采集、Goertzel算法、“1分钟定时”状态机、UART数据上报。",
        "dependency": "无需硬件板，仅需JLink调试器。"
      },
      "phase_2 (2天)": {
        "task": "开始编写BSP驱动(STARTUP_ASM, HAL_Init, GPIO, UART, IWDG, TIM, ADC, DMA)。与Phase 1并行，因为引脚配置与原理图相关。",
        "dependency": "硬件原理图 (已有)"
      },
      "phase_3 (3天)": {
        "task": "将Phase 1已验证的核心算法移植并集成到Phase 2的BSP测试版上。启动SIL测试。"
      },
      "critical_path": "硬件板回来(焊接)-> 首次上电 -> 验证电源 + 调试口 -> 下载固件 -> 验证UART通信 -> 验证ADC采样 -> 集成测试。预计硬件回板后需要2天才能看到第一个有效数据。"
    }
  },
  "critical_risks": [
    {
      "risk_id": "R1",
      "failure_mode": "RC网络相位延迟校准失败",
      "severity": "High (9)",
      "occurrence": "Medium (4)",
      "detection": "Low (3)",
      "rpn": 108,
      "mitigation": "在SIL中增加纯数学仿真；在HIL中用精确信号源和示波器测量实际相位差，建立查表或公式补偿。"
    },
    {
      "risk_id": "R2",
      "failure_mode": "RAM/Flash 空间不足",
      "severity": "High (8)",
      "occurrence": "High (6)",
      "detection": "Medium (4)",
      "rpn": 192,
      "mitigation": "严格按资源预算表分配，禁用HAL库中未使用的外设模块，使用LL驱动替代部分HAL代码以节省Flash。"
    },
    {
      "risk_id": "R3",
      "failure_mode": "BSP中DS18B20时序不符合Spec",
      "severity": "Medium (7)",
      "occurrence": "Medium (5)",
      "detection": "Low (3)",
      "rpn": 105,
      "mitigation": "直接操作GPIO寄存器实现1-Wire时序，并严格对准数据手册要求的微秒级时序窗口。在-20°C ~ 60°C下验证。"
    }
  ],
  "test_strategy_matrix": {
    "sil_test_cases": [
      "输入已知的正弦波序列，验证DFT计算结果RMS误差 < 1%",
      "输入带10%噪声的正弦波，验证异常检测器能正确识别",
      "模拟UART协议帧，验证解析器不会因错误帧而崩溃"
    ],
    "hil_test_cases": [
      "用信号发生器输入1kHz, 100mVpp正弦波，测量内阻计算值",
      "用电子负载模拟48mΩ电池，测量内阻，验证线性度",
      "断开并重连DS18B20，观察系统状态跃迁",
      "在总线上发送CRC错误帧，测试从机能否正常恢复"
    ],
    "fault_injection_tests": [
      "IWDG喂狗失败情况下，能否在200ms内重启系统",
      "UART接收缓冲区满后，是否发生溢出并丢弃新数据",
      "在ADC测量期间，模拟掉电，系统能否通过BOR及时复位"
    ]
  },
  "open_questions": [
    "Q1: 恒流源电路 (U8/U9/U10/U11) 的具体型号和增益是多少？这将直接影响ADC采样的量程和分辨率。",
    "Q2: RC滤波网络 (R18=100k, C4=1nF) 的截止频率约1.6kHz，但相位延迟达45°。这个相位延迟是否在可校准范围内？是否需要增加一个补偿电路？",
    "Q3: 主机何时/如何给从机分配唯一地址？是在系统上电时通过广播帧自动分配，还是需要在生产过程中通过某种方式预置？",
    "Q4: 测量结果是否需要本地保存？如果需要，8KB的RAM可能需要外部EEPROM (如I2C) 来存储历史数据，但硬件上没有。",
    "Q5: 用户期望的测量精度（内阻）是多少？这决定了ADC的有效位数（ENOB）和运放的噪声指标。"
  ]
}
```