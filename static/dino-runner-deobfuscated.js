/**
 * Chrome Dino Runner (T-Rex Runner) - 去混淆版本
 * ===============================================
 * 原始代码来源：Chrome 离线页面的恐龙跑酷游戏
 * 本文件为去混淆、重构并添加中文注释后的版本
 *
 * 游戏组件结构：
 * - Runner: 主游戏引擎，管理游戏循环、状态、事件
 * - Trex: 恐龙角色（跳跃、蹲下、碰撞检测）
 * - Horizon: 地平线管理器（障碍物、云朵、星星、月亮）
 * - HorizonLine: 地面线条
 * - Obstacle: 障碍物（仙人掌、翼龙）
 * - Cloud: 背景云朵
 * - DistanceMeter: 距离/分数显示
 * - GameOverPanel: 游戏结束面板
 */

(function() {
    'use strict';

    // ==================== 工具函数 ====================

    /**
     * 生成指定范围内的随机整数
     * @param {number} min - 最小值
     * @param {number} max - 最大值
     * @returns {number} 随机整数
     */
    function getRandomNum(min, max) {
        return Math.floor(Math.random() * (max - min + 1)) + min;
    }

    /**
     * 创建碰撞检测盒子（矩形）
     * @param {number} x - X坐标
     * @param {number} y - Y坐标
     * @param {number} width - 宽度
     * @param {number} height - 高度
     */
    function CollisionBox(x, y, width, height) {
        this.x = x;
        this.y = y;
        this.width = width;
        this.height = height;
    }

    /**
     * 检测两个碰撞盒子是否相交
     * @param {CollisionBox} box1 - 第一个碰撞盒
     * @param {CollisionBox} box2 - 第二个碰撞盒
     * @returns {boolean} 是否碰撞
     */
    function checkCollision(box1, box2) {
        var collided = false;
        var box2X = box2.x;
        // AABB碰撞检测：两个矩形在所有轴上都重叠则发生碰撞
        if (box1.x < box2X + box2.width &&
            box1.x + box1.width > box2X &&
            box1.y < box2.y + box2.height &&
            box1.height + box1.y > box2.y) {
            collided = true;
        }
        return collided;
    }

    /**
     * 获取两个碰撞盒子的偏移和（用于复合碰撞检测）
     * @param {CollisionBox} a - 碰撞盒A
     * @param {CollisionBox} b - 碰撞盒B
     * @returns {CollisionBox} 合并后的碰撞盒
     */
    function collideBoxSum(a, b) {
        return new CollisionBox(a.x + b.x, a.y + b.y, a.width, a.height);
    }

    /**
     * 获取当前时间戳（毫秒），兼容不同浏览器
     * @returns {number} 时间戳
     */
    function getTimeStamp() {
        return window.performance ?
            (new Date()).getTime() : // 回退方案
            Date.now();              // 优先使用高精度时间
    }

    /**
     * 检测是否为移动端设备
     */
    var isMobile = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
    var isIOS = /iPad|iPhone|iPod/.test(navigator.platform) || isMobile;

    // ==================== 默认配置 ====================

    /**
     * 游戏全局配置
     */
    var DEFAULT_CONFIG = {
        // 加速度系数（每帧增加的速度）
        ACCELERATION: 0.001,
        // 背景云朵速度系数
        BG_CLOUD_SPEED: 0.2,
        // 底部内边距
        BOTTOM_PAD: 10,
        // 清除时间
        CLEAR_TIME: 3000,
        // 云朵出现频率
        CLOUD_FREQUENCY: 0.5,
        // 游戏结束面板淡入时间
        GAMEOVER_CLEAR_TIME: 750,
        // 初始跳跃速度（负值=向上）
        GAP_COEFFICIENT: 0.6,
        // 重力加速度
        GRAVITY: 0.6,
        // 开场动画持续时间
        INTRO_DURATION: 1500,
        // 倒置淡入持续时间
        INVERT_FADE_DURATION: 12000,
        // 倒置距离
        INVERT_DISTANCE: 700,
        // 最大障碍物重复数
        MAX_OBSTACLE_DUPLICATION: 2,
        // 最大障碍物长度
        MAX_OBSTACLE_LENGTH: 3,
        // 最大闪烁次数
        MAX_BLINK_COUNT: 3,
        // 最大云朵间隙
        MAX_CLOUD_GAP: 400,
        // 最大间隙系数
        MAX_GAP_COEFFICIENT: 1.5,
        // 最大跳跃高度
        MAX_JUMP_HEIGHT: 30,
        // 最小云朵间隙
        MIN_CLOUD_GAP: 100,
        // 最小跳跃高度
        MIN_JUMP_HEIGHT: 30,
        // 移动端速度系数
        MOBILE_SPEED_COEFFICIENT: 1.2,
        // 展示的资源模板ID
        RESOURCE_TEMPLATE_ID: 'audio-resources',
        // 速度（初始游戏速度，像素/帧）
        SPEED: 6,
        // 速度下降系数
        SPEED_DROP_COEFFICIENT: 3,
        // 弧线/曲线阈值
        ARCADE_MODE_URL: 'chrome://dino',
    };

    /**
     * 默认画布尺寸
     */
    var DEFAULT_DIMENSIONS = {
        WIDTH: 600,  // 默认宽度
        HEIGHT: 150, // 默认高度
    };

    /**
     * CSS类名映射
     */
    var CLASSES = {
        // 主容器类名
        CONTAINER: 'runner-container',
        // 画布类名
        CANVAS: 'runner-canvas',
        // 游戏状态类名
        PLAYING: 'playing',
        // 暂停状态
        PAUSED: 'paused',
        // 崩溃状态
        CRASHED: 'crashed',
        // 触控控制器
        TOUCH_CONTROLLER: 'touch-controller',
        // 小吃栏
        SNACKBAR: 'snackbar',
        SNACKBAR_SHOW: 'snackbar-show',
        // 禁用状态
        DISABLED: 'disabled',
        // 错误页控制器
        ERROR_PAGE_CONTROLLER: 'error-page-controller',
    };

    /**
     * 精灵图定义（低DPI屏幕）
     * 每个精灵定义了在原始图片中的位置和尺寸
     */
    var SPRITE_DEFINITION_LDPI = {
        // 仙人掌-大型
        CACTUS_LARGE: { x: 332, y: 2 },
        // 仙人掌-小型
        CACTUS_SMALL: { x: 228, y: 2 },
        // 云朵
        CLOUD: { x: 86, y: 2 },
        // 地平线/地面
        HORIZON: { x: 2, y: 54 },
        // 月亮
        MOON: { x: 484, y: 2 },
        // 翼龙
        PTERODACTYL: { x: 134, y: 2 },
        // 重启按钮
        RESTART: { x: 2, y: 2 },
        // 文字精灵
        TEXT_SPRITE: { x: 655, y: 2 },
        // 恐龙-默认
        TREX: { x: 848, y: 2 },
        // 星星
        STAR: { x: 645, y: 2 },
    };

    /**
     * 精灵图定义（高DPI/Retina屏幕）
     */
    var SPRITE_DEFINITION_HDPI = {
        CACTUS_LARGE: { x: 652, y: 2 },
        CACTUS_SMALL: { x: 446, y: 2 },
        CLOUD: { x: 166, y: 2 },
        HORIZON: { x: 2, y: 104 },
        MOON: { x: 954, y: 2 },
        PTERODACTYL: { x: 260, y: 2 },
        RESTART: { x: 2, y: 2 },
        TEXT_SPRITE: { x: 1276, y: 2 },
        TREX: { x: 1678, y: 2 },
        STAR: { x: 1294, y: 2 },
    };

    /**
     * 声音资源模板
     */
    var SOUNDS_TEMPLATE = {
        BUTTON_PRESS: 'offline-sound-press',
        HIT: 'offline-sound-hit',
        SCORE: 'offline-sound-reached',
    };

    /**
     * 键盘事件映射
     */
    var KEYCODES = {
        // 跳跃按键
        JUMP: { '38': 1, '32': 1 },   // 上箭头、空格
        // 蹲下按键
        DUCK: { '40': 1 },             // 下箭头
        // 重启按键
        RESTART: { '13': 1 },          // 回车
    };

    /**
     * 事件名称常量
     */
    var EVENTS = {
        ANIM_END: 'webkitAnimationEnd',
        CLICK: 'click',
        KEYDOWN: 'keydown',
        KEYUP: 'keyup',
        MOUSEDOWN: 'mousedown',
        MOUSEUP: 'mouseup',
        RESIZE: 'resize',
        TOUCHEND: 'touchend',
        TOUCHSTART: 'touchstart',
        VISIBILITY: 'visibilitychange',
        BLUR: 'blur',
        FOCUS: 'focus',
        LOAD: 'load',
    };

    // ==================== Runner（主游戏引擎） ====================

    /**
     * Runner 构造函数 - 游戏主控制器
     *
     * 负责：
     * - 管理游戏循环（requestAnimationFrame）
     * - 处理输入事件（键盘、触摸、鼠标）
     * - 协调各个子组件（恐龙、地平线、分数等）
     * - 管理游戏状态（等待、游戏中、崩溃）
     *
     * @param {string} outerContainerId - 外层容器ID选择器
     * @param {Object} optConfig - 可选的配置覆盖
     */
    function Runner(outerContainerId, optConfig) {
        // 单例模式：确保只有一个Runner实例
        if (Runner.instance_) {
            return Runner.instance_;
        }
        Runner.instance_ = this;

        // 获取外层容器元素
        this.outerContainerEl = document.querySelector(outerContainerId);
        // 获取游戏主容器
        this.containerEl = null;
        // 配置合并
        this.config = optConfig || Runner.config;

        // 画布相关
        this.canvas = null;
        this.canvasCtx = null;

        // 子组件
        this.tRex = null;           // 恐龙角色
        this.horizon = null;        // 地平线管理器
        this.distanceMeter = null;  // 距离计量器
        this.distanceRan = 0;       // 总跑步距离

        // 游戏状态
        this.playing = false;       // 是否正在游戏
        this.paused = false;        // 是否暂停
        this.crashed = false;       // 是否撞到障碍物
        this.activated = false;     // 是否已激活（第一次点击/按键后激活）
        this.playingIntro = false;  // 是否正在播放开场动画

        // 时间相关
        this.msPerFrame = 1000 / 60;    // 每帧毫秒数（60FPS）
        this.currentSpeed = this.config.SPEED;  // 当前游戏速度
        this.time = 0;              // 累计游戏时间

        // 其他状态
        this.obstacles = [];        // 活跃的障碍物列表
        this.inverted = false;      // 是否处于倒置模式（昼夜反转）
        this.invertTimer = 0;       // 倒置计时器
        this.resizeTimerId_ = null; // 窗口大小调整防抖定时器

        // 最高分
        this.highestScore = 0;

        // 闪烁效果
        this.flashTimer = 0;        // 闪烁计时器
        this.flashIterations = 0;   // 闪烁次数

        // 音频
        this.audioContext = null;
        this.soundFx = {};          // 音效缓冲区映射
        this.audioResourceCount = 0;

        // 初始化：检测是否支持该功能，然后启动
        if (this.isDisabled()) {
            this.setupDisabledRunner();
        } else {
            this.loadImages();
        }
    }

    /**
     * 默认游戏运行配置
     */
    Runner.config = {
        ACCELERATION: 0.001,
        BG_CLOUD_SPEED: 0.2,
        BOTTOM_PAD: 10,
        CLEAR_TIME: 3000,
        CLOUD_FREQUENCY: 0.5,
        GAMEOVER_CLEAR_TIME: 750,
        GAP_COEFFICIENT: 0.6,
        GRAVITY: 0.6,
        INTRO_DURATION: 1500,
        INVERT_FADE_DURATION: 12000,
        INVERT_DISTANCE: 700,
        MAX_BLINK_COUNT: 3,
        MAX_CLOUD_GAP: 400,
        MAX_GAP_COEFFICIENT: 1.5,
        MAX_JUMP_HEIGHT: 30,
        MAX_OBSTACLE_DUPLICATION: 2,
        MAX_OBSTACLE_LENGTH: 3,
        MIN_CLOUD_GAP: 100,
        MIN_JUMP_HEIGHT: 30,
        MOBILE_SPEED_COEFFICIENT: 1.2,
        RESOURCE_TEMPLATE_ID: 'audio-resources',
        SPEED: 6,
        SPEED_DROP_COEFFICIENT: 3,
    };

    Runner.classes = CLASSES;
    Runner.events = EVENTS;
    Runner.keycodes = KEYCODES;
    Runner.sounds = SOUNDS_TEMPLATE;

    /**
     * 检查游戏是否被禁用（例如在错误页面之外）
     * @returns {boolean}
     */
    Runner.prototype.isDisabled = function() {
        return false;
    };

    /**
     * 设置禁用状态的Runner（显示静态图标）
     */
    Runner.prototype.setupDisabledRunner = function() {
        // 创建图标容器
        this.containerEl = document.createElement('div');
        this.containerEl.className = Runner.classes.SNACKBAR;
        this.containerEl.textContent = '🐱‍👤'; // 显示一个图标
        this.outerContainerEl.appendChild(this.containerEl);

        // 显示小吃栏
        document.addEventListener(Runner.events.ANIM_END, function(e) {
            if (Runner.keycodes.JUMP[e.keyCode] &&
                this.containerEl.classList.contains(Runner.classes.SNACKBAR_SHOW)) {
                this.containerEl.classList.add('snackbar-hide');
            }
        }.bind(this));
    };

    /**
     * 更新配置参数
     * @param {string} key - 配置键名
     * @param {*} value - 新值
     */
    Runner.prototype.updateConfigSetting = function(key, value) {
        if (key in this.config && value !== undefined) {
            this.config[key] = value;
            switch (key) {
                case 'GRAVITY':
                case 'SPEED_DROP_COEFFICIENT':
                    // 这些参数影响恐龙行为，需要同步更新
                    this.tRex.config[key] = value;
                    break;
                case 'INVERT_DISTANCE':
                    // 更新倒置距离需要重置跳跃速度
                    this.tRex.setJumpVelocity(value);
                    break;
                case 'SPEED':
                    // 更新速度
                    this.setSpeed(value);
                    break;
            }
        }
    };

    /**
     * 加载游戏图片资源
     */
    Runner.prototype.loadImages = function() {
        // 根据屏幕DPI选择合适的精灵图
        if (this.isHidpi()) {
            // 高DPI屏幕：使用2x分辨率图片
            Runner.imageSprite = document.getElementById('offline-resources-2x');
            this.spriteDef = SPRITE_DEFINITION_HDPI;
        } else {
            // 标准DPI屏幕
            Runner.imageSprite = document.getElementById('offline-resources-1x');
            this.spriteDef = SPRITE_DEFINITION_LDPI;
        }

        // 如果精灵图还未加载完成，等待加载
        if (Runner.imageSprite.complete) {
            this.init();
        } else {
            Runner.imageSprite.addEventListener(EVENTS.LOAD, this.init.bind(this));
        }
    };

    /**
     * 加载音频资源
     */
    Runner.prototype.loadSounds = function() {
        // 如果不支持Web Audio API则跳过
        if (!isIOS) {
            // 创建音频上下文
            this.audioContext = new AudioContext();

            // 从DOM中获取音频模板
            var resourceTemplate = document.getElementById(this.config.RESOURCE_TEMPLATE_ID).content;

            // 遍历所有音效定义
            for (var soundKey in Runner.sounds) {
                var soundSrc = resourceTemplate.getElementById(Runner.sounds[soundKey]).src;
                soundSrc = soundSrc.substr(soundSrc.indexOf(',') + 1);
                var audioBuffer = base64ToArrayBuffer(soundSrc);

                // 解码音频数据
                this.audioContext.decodeAudioData(audioBuffer, function(buffer) {
                    this.soundFx[soundKey] = buffer;
                }.bind(this, soundKey));
            }
        }
    };

    /**
     * 设置/调整游戏速度
     * @param {number} speed - 像素/帧的速度值。可选，不传则使用默认值
     */
    Runner.prototype.setSpeed = function(speed) {
        var newSpeed = speed || this.currentSpeed;

        // 在移动设备上应用速度系数
        if (600 > this.config.WIDTH) {
            var mobileSpeed = newSpeed * this.config.WIDTH / 600 * this.config.MOBILE_SPEED_COEFFICIENT;
            this.currentSpeed = mobileSpeed > newSpeed ? newSpeed : mobileSpeed;
        } else if (speed) {
            this.currentSpeed = newSpeed;
        }
    };

    /**
     * 游戏初始化 - 创建所有DOM元素和游戏组件
     */
    Runner.prototype.init = function() {
        // 隐藏加载中的小吃栏
        var snackbarEl = document.querySelector('.' + Runner.classes.SNACKBAR);
        if (snackbarEl) {
            snackbarEl.style.display = 'none';
        }

        // 更新画布尺寸适配
        this.adjustDimensions();
        this.setSpeed();

        // 创建游戏主容器
        this.containerEl = document.createElement('div');
        this.containerEl.className = Runner.classes.CANVAS;

        // 创建画布
        var canvas = document.createElement('canvas');
        canvas.className = Runner.classes.CONTAINER + ' ' +
            (Runner.classes.CONTAINER || '');
        canvas.width = this.config.WIDTH;
        canvas.height = this.config.HEIGHT;

        // 更新画布缩放比例（高清屏适配）
        Runner.updateCanvasScaling(canvas);

        // 获取2D渲染上下文
        this.canvas = canvas;
        this.canvasCtx = canvas.getContext('2d');
        this.canvasCtx.fillStyle = '#f7f7f7';
        this.canvasCtx.fill(); // 填充背景色

        // 创建子组件
        // 地平线管理器 - 负责背景、障碍物、云朵等
        this.horizon = new Horizon(this.canvas, this.spriteDef, this.config, this.config.GRAVITY);

        // 距离计量器 - 显示分数
        this.distanceMeter = new DistanceMeter(this.canvas, this.spriteDef.TEXT_SPRITE, this.config.WIDTH);

        // 恐龙角色
        this.tRex = new Trex(this.canvas, this.spriteDef.TREX);

        // 将画布添加到容器
        this.containerEl.appendChild(canvas);

        // 将容器添加到外层容器
        this.outerContainerEl.appendChild(this.containerEl);

        // 如果是移动端，添加触摸控制器
        if (isMobile) {
            this.createTouchController();
        }

        // 开始监听事件
        this.startListening();
        // 启动游戏循环
        this.update();

        // 监听窗口大小变化
        window.addEventListener(EVENTS.RESIZE, this.debounceResize.bind(this));
    };

    /**
     * 创建移动端触摸控制器
     */
    Runner.prototype.createTouchController = function() {
        this.touchController = document.createElement('div');
        this.touchController.className = Runner.classes.TOUCH_CONTROLLER;
        this.outerContainerEl.appendChild(this.touchController);
    };

    /**
     * 窗口大小调整的防抖处理
     */
    Runner.prototype.debounceResize = function() {
        // 清除之前的定时器
        if (this.resizeTimerId_) {
            clearInterval(this.resizeTimerId_);
        }
        // 设置新的定时器（防抖）
        this.resizeTimerId_ = setInterval(this.adjustDimensions.bind(this), 250);
    };

    /**
     * 调整画布尺寸以适配屏幕
     */
    Runner.prototype.adjustDimensions = function() {
        // 清除调整定时器
        clearInterval(this.resizeTimerId_);
        this.resizeTimerId_ = null;

        // 计算可用宽度（减去内边距）
        var paddingLeft = parseInt(window.getComputedStyle(this.outerContainerEl).paddingLeft);
        paddingLeft = Number(paddingLeft.substr(0, paddingLeft.length - 2));
        this.config.WIDTH = this.outerContainerEl.offsetWidth - 2 * paddingLeft;

        // 更新画布
        if (this.canvas) {
            this.canvas.width = this.config.WIDTH;
            this.canvas.height = this.config.HEIGHT;
            Runner.updateCanvasScaling(this.canvas);

            // 通知各组件尺寸变化
            this.distanceMeter.calcXPos(this.config.WIDTH);
            this.clearCanvas();
            this.horizon.update(0, 0, true);
            this.tRex.update(0);

            // 崩溃或暂停状态下的特殊处理
            if (this.playingIntro || this.crashed || this.paused) {
                this.containerEl.style.width = this.config.WIDTH + 'px';
                this.containerEl.style.height = this.config.HEIGHT + 'px';
                this.distanceMeter.update(0, Math.ceil(this.distanceRan));
                this.stop();
            } else {
                this.tRex.update(0, Trex.status.WAITING);
            }

            // 游戏结束面板也需要更新
            if (this.crashed && this.gameOverPanel) {
                this.gameOverPanel.updateDimensions(this.config.WIDTH);
                this.gameOverPanel.draw();
            }
        }
    };

    /**
     * 播放开场动画（从图标过渡到游戏）
     */
    Runner.prototype.playIntro = function() {
        // 如果已经暂停或游戏结束则跳过
        if (this.activated || this.crashed) {
            if (this.crashed) {
                this.restart();
            }
            return;
        }

        // 开始播放
        this.playingIntro = true;
        this.tRex.playingIntro = true;

        // 创建CSS动画关键帧：从图标大小过渡到游戏宽度
        var keyframes = '@-webkit-keyframes intro { ' +
            'from { width:' + Trex.config.WIDTH + 'px }' +
            'to { width: ' + this.config.WIDTH + 'px }' +
            '}';
        var stylesheet = document.createElement('style');
        stylesheet.innerHTML = keyframes;
        document.head.appendChild(stylesheet);

        // 监听动画结束事件
        this.containerEl.addEventListener(Runner.events.ANIM_END, this.startGame.bind(this));

        // 应用动画
        this.containerEl.style.webkitAnimation = 'intro .4s ease-out 1 both';
        this.containerEl.style.width = this.config.WIDTH + 'px';

        // 标记已激活
        this.activated = true;
        this.playing = true;
    };

    /**
     * 开场动画结束后正式启动游戏
     */
    Runner.prototype.startGame = function() {
        // 重置距离
        this.distanceRan = 0;
        // 标记开场动画结束
        this.playingIntro = false;
        this.tRex.playingIntro = false;

        // 移除动画属性
        this.containerEl.style.webkitAnimation = '';

        // 增加游戏次数计数器
        this.playCount++;

        // 重新监听失焦和页面可见性事件
        document.addEventListener(EVENTS.KEYUP, this.onVisibilityChange.bind(this));
        window.addEventListener(EVENTS.BLUR, this.onVisibilityChange.bind(this));
        window.addEventListener(EVENTS.FOCUS, this.onVisibilityChange.bind(this));
    };

    /**
     * 清除画布内容
     */
    Runner.prototype.clearCanvas = function() {
        this.canvasCtx.clearRect(0, 0, this.config.WIDTH, this.config.HEIGHT);
    };

    /**
     * 主游戏循环更新函数
     * 每帧调用，驱动整个游戏逻辑
     */
    Runner.prototype.update = function() {
        // 记录更新状态，防止重复调度
        this.updatePending = false;

        var now = getTimeStamp();
        var deltaTime = now - (this.time || now);
        this.time = now;

        if (this.playing) {
            // === 游戏进行中的逻辑 ===
            this.clearCanvas();

            // 更新恐龙
            if (this.tRex.jumping) {
                this.tRex.updateJump(deltaTime);
            }

            // 累计跑步距离
            this.distanceRan += this.currentSpeed * deltaTime / this.msPerFrame;

            // 速度随距离逐渐增加
            if (this.currentSpeed < this.config.MAX_SPEED) {
                this.currentSpeed += this.config.ACCELERATION;
            }

            // 判断是否需要触发倒置模式（昼夜转换）
            var invertTrigger = !this.inverted && this.distanceRan > this.config.INVERT_DISTANCE;
            if (this.playingIntro || invertTrigger || this.activated) {
                // 更新地平线（背景、障碍物等）
                var showInverted = this.inverted;
                var horizonDelta = this.playingIntro ? 0 : deltaTime;
                this.horizon.update(horizonDelta, this.currentSpeed, showInverted);
            }

            // === 碰撞检测 ===
            if (invertTrigger) {
                this.invert(true); // 触发昼夜反转
            }

            // 获取恐龙的碰撞盒
            var tRexBox, obstacleBox;

            if (this.horizon.obstacles.length > 0) {
                var obstacle = this.horizon.obstacles[0];
                var trex = this.tRex;

                // 创建恐龙的碰撞区域
                tRexBox = new CollisionBox(
                    trex.xPos + 1,
                    trex.yPos + 1,
                    trex.config.WIDTH - 2,
                    trex.config.HEIGHT - 2
                );

                // 创建障碍物的碰撞区域
                obstacleBox = new CollisionBox(
                    obstacle.xPos + 1,
                    obstacle.yPos + 1,
                    obstacle.typeConfig.width * obstacle.size - 2,
                    obstacle.typeConfig.height - 2
                );

                // 调试：检测碰撞盒
                if (checkCollision(tRexBox, obstacleBox)) {
                    // 进一步精确检测：使用子碰撞盒
                    var tRexCollisionBoxes = trex.collisionBoxes;
                    var obstacleCollisionBoxes = obstacle.collisionBoxes;

                    // 获取当前状态的碰撞盒
                    var tRexBoxes = trex.ducking ? Trex.collisionBoxes.DUCKING : Trex.collisionBoxes.RUNNING;

                    var collided = false;
                    for (var i = 0; i < tRexBoxes.length; i++) {
                        for (var j = 0; j < obstacleCollisionBoxes.length; j++) {
                            var trexBoxAdj = collideBoxSum(tRexBoxes[i], tRexBox);
                            var obstacleBoxAdj = collideBoxSum(obstacleCollisionBoxes[j], obstacleBox);

                            if (checkCollision(trexBoxAdj, obstacleBoxAdj)) {
                                collided = true;
                                break;
                            }
                        }
                        if (collided) break;
                    }

                    if (collided) {
                        this.gameOver(); // 游戏结束！
                    }
                }
            }

            // 更新距离显示
            this.distanceMeter.update(deltaTime, Math.ceil(this.distanceRan));

            // 检测是否达成成就距离
            if (this.distanceRan > this.config.ACHIEVEMENT_DISTANCE &&
                this.distanceMeter.getActualDistance(Math.ceil(this.distanceRan)) > 0) {
                // 显示成就
                this.playSound(this.soundFx.SCORE);
            }

            // 闪烁效果计时器
            if (this.flashTimer > this.config.FLASH_DURATION) {
                this.flashTimer = 0;
                this.flashIterations = 0;
                this.setBlinkDelay(false);
            } else if (this.flashTimer) {
                this.flashTimer += deltaTime;
            } else {
                // 检测是否需要开始闪烁（分数达到特定值时）
                var distance = this.distanceMeter.getActualDistance(Math.ceil(this.distanceRan));
                if (distance > 0) {
                    this.flashIterations = !(distance % this.config.FLASH_ITERATIONS);
                    if (this.flashTimer === 0 && this.flashIterations) {
                        this.flashTimer += deltaTime;
                        this.setBlinkDelay(true);
                    }
                }
            }
        }

        // 更新恐龙动画（无论游戏状态）
        if (this.playing || (!this.activated && this.tRex.playCount < Runner.config.MAX_BLINK_COUNT)) {
            this.tRex.update(deltaTime);
            this.scheduleNextUpdate();
        }
    };

    /**
     * 处理DOM事件分发
     * @param {Event} e - DOM事件
     */
    Runner.prototype.handleEvent = function(e) {
        switch (e.type) {
            case EVENTS.KEYDOWN:
            case EVENTS.TOUCHSTART:
            case EVENTS.MOUSEDOWN:
                this.onKeyDown(e);
                break;
            case EVENTS.KEYUP:
            case EVENTS.TOUCHEND:
            case EVENTS.MOUSEUP:
                this.onKeyUp(e);
                break;
        }
    };

    /**
     * 开始事件监听
     */
    Runner.prototype.startListening = function() {
        // 键盘事件
        document.addEventListener(EVENTS.KEYDOWN, this);
        document.addEventListener(EVENTS.KEYUP, this);

        if (isMobile) {
            // 移动端触摸事件
            this.touchController.addEventListener(EVENTS.TOUCHSTART, this);
            this.touchController.addEventListener(EVENTS.TOUCHEND, this);
            this.containerEl.addEventListener(EVENTS.TOUCHSTART, this);
        } else {
            // 桌面端鼠标事件
            document.addEventListener(EVENTS.MOUSEDOWN, this);
            document.addEventListener(EVENTS.MOUSEUP, this);
        }
    };

    /**
     * 停止事件监听
     */
    Runner.prototype.stopListening = function() {
        document.removeEventListener(EVENTS.KEYDOWN, this);
        document.removeEventListener(EVENTS.KEYUP, this);

        if (isMobile) {
            this.touchController.removeEventListener(EVENTS.TOUCHSTART, this);
            this.touchController.removeEventListener(EVENTS.TOUCHEND, this);
            this.containerEl.removeEventListener(EVENTS.TOUCHSTART, this);
        } else {
            document.removeEventListener(EVENTS.MOUSEDOWN, this);
            document.removeEventListener(EVENTS.MOUSEUP, this);
        }
    };

    /**
     * 按键按下事件处理
     * @param {Event} e - 键盘/触摸事件
     */
    Runner.prototype.onKeyDown = function(e) {
        // 防止页面滚动（方向键）
        if (isMobile && this.playing) {
            e.preventDefault();
        }

        // 检查事件目标是否在游戏画布上
        if (e.target != this.canvas) {
            // 如果不是游戏内的输入...
            if (!this.crashed && !Runner.keycodes.JUMP[e.keyCode] &&
                e.type != EVENTS.TOUCHSTART) {
                return;
            }

            // 如果游戏还没有激活，先激活
            if (!this.playing) {
                this.loadSounds();
                this.playing = true;
                this.update();
                if (window.errorPageController) {
                    errorPageController.trackEasterEgg();
                }
            }

            // 如果恐龙没有在跳跃或蹲下
            if (!this.tRex.jumping && !this.tRex.ducking) {
                this.playSound(this.soundFx.BUTTON_PRESS);
                this.tRex.startJump(this.currentSpeed);
            }
        }

        // 如果在崩溃状态，检查是否是点击画布来重启
        if (this.crashed && e.type == EVENTS.TOUCHSTART &&
            e.currentTarget == this.containerEl) {
            this.restart();
        }

        // 活跃状态下的快捷操作
        if (this.playing && !this.crashed && Runner.keycodes.DUCK[e.keyCode]) {
            e.preventDefault();
            if (this.tRex.jumping) {
                // 跳跃中快速下落
                this.tRex.setSpeedDrop();
            } else if (!this.tRex.jumping && !this.tRex.ducking) {
                // 蹲下
                this.tRex.setDuck(true);
            }
        }
    };

    /**
     * 按键释放事件处理
     * @param {Event} e - 键盘/触摸事件
     */
    Runner.prototype.onKeyUp = function(e) {
        var keyCode = String(e.keyCode);
        var isJumpKey = Runner.keycodes.JUMP[keyCode] ||
            e.type == EVENTS.TOUCHEND ||
            e.type == EVENTS.MOUSEUP;

        if (this.isRunning() && isJumpKey) {
            // 释放跳跃键：控制跳跃高度
            this.tRex.endJump();
        } else if (Runner.keycodes.DUCK[keyCode]) {
            // 释放蹲下键
            this.tRex.speedDrop = false;
            this.tRex.setDuck(false);
        } else if (this.crashed) {
            // 崩溃后按任意键重启的条件
            var deltaTime = getTimeStamp() - this.time;
            if ((Runner.keycodes.RESTART[keyCode] || this.isLeftClickOnCanvas(e)) &&
                deltaTime >= this.config.GAMEOVER_CLEAR_TIME &&
                Runner.keycodes.JUMP[keyCode]) {
                this.restart();
            }
        } else if (this.paused && isJumpKey) {
            // 暂停状态恢复
            this.tRex.reset();
            this.play();
        }
    };

    /**
     * 检测是否是画布上的左键点击
     * @param {Event} e
     * @returns {boolean}
     */
    Runner.prototype.isLeftClickOnCanvas = function(e) {
        return e.button != null && e.button < 2 &&
            e.type == EVENTS.MOUSEUP && e.target == this.canvas;
    };

    /**
     * 调度下一次更新
     */
    Runner.prototype.scheduleNextUpdate = function() {
        if (!this.updatePending) {
            this.updatePending = true;
            this.raqId = requestAnimationFrame(this.update.bind(this));
        }
    };

    /**
     * 判断游戏是否正在运行
     * @returns {boolean}
     */
    Runner.prototype.isRunning = function() {
        return !!this.raqId;
    };

    /**
     * 游戏结束处理
     */
    Runner.prototype.gameOver = function() {
        // 播放碰撞音效
        this.playSound(this.soundFx.HIT);

        // 如果支持振动（移动端），触发振动反馈
        if (isMobile && navigator.vibrate) {
            navigator.vibrate(200);
        }

        this.stop();            // 停止游戏循环
        this.crashed = true;    // 标记为崩溃状态
        this.distanceMeter.acheivement = false;

        // 恐龙播放死亡动画
        this.tRex.update(100, Trex.status.CRASHED);

        // 显示游戏结束面板
        if (!this.gameOverPanel) {
            this.gameOverPanel = new GameOverPanel(
                this.canvas,
                this.spriteDef.TEXT_SPRITE,
                this.spriteDef.RESTART,
                this.config
            );
        } else {
            this.gameOverPanel.draw();
        }

        // 更新最高分
        if (this.distanceRan > this.highestScore) {
            this.highestScore = Math.ceil(this.distanceRan);
            this.distanceMeter.setHighScore(this.highestScore);
        }

        // 记录碰撞时间
        this.time = getTimeStamp();
    };

    /**
     * 停止游戏循环
     */
    Runner.prototype.stop = function() {
        this.playing = false;
        this.paused = true;
        cancelAnimationFrame(this.raqId);
        this.raqId = 0;
    };

    /**
     * 恢复游戏
     */
    Runner.prototype.play = function() {
        if (!this.crashed) {
            this.playing = true;
            this.paused = false;
            this.tRex.update(0, Trex.status.RUNNING);
            this.time = getTimeStamp();
            this.update();
        }
    };

    /**
     * 重启游戏
     */
    Runner.prototype.restart = function() {
        if (!this.raqId) {
            this.playCount++;
            this.distanceRan = 0;
            this.playing = true;
            this.crashed = false;
            this.distanceRan = 0;
            this.setSpeed(this.config.SPEED);
            this.time = getTimeStamp();

            // 移除游戏结束状态样式
            this.containerEl.classList.remove(Runner.classes.CRASHED);

            // 清理画布
            this.clearCanvas();
            this.distanceMeter.reset(this.highestScore);
            this.horizon.reset();
            this.tRex.reset();

            // 播放按钮音效
            this.playSound(this.soundFx.BUTTON_PRESS);

            this.setBlinkDelay(true);
            this.update();
        }
    };

    /**
     * 处理页面可见性变化（用户切换标签页等）
     * @param {Event} e
     */
    Runner.prototype.onVisibilityChange = function(e) {
        if (document.hidden || document.webkitHidden || e.type == 'blur' ||
            e.type == EVENTS.KEYUP && e.keyCode != KEYCODES.JUMP) {
            this.stop(); // 页面不可见时暂停
        } else if (!this.crashed) {
            this.tRex.reset();
            this.play(); // 页面恢复可见时继续
        }
    };

    /**
     * 播放音效
     * @param {AudioBuffer} soundBuffer - 音频缓冲区
     */
    Runner.prototype.playSound = function(soundBuffer) {
        if (soundBuffer) {
            var sourceNode = this.audioContext.createBufferSource();
            sourceNode.buffer = soundBuffer;
            sourceNode.connect(this.audioContext.destination);
            sourceNode.start(0);
        }
    };

    /**
     * 切换倒置模式（昼夜反转效果）
     * @param {boolean} reset - 是否强制重置
     */
    Runner.prototype.setBlinkDelay = function(reset) {
        if (reset) {
            // 重置闪烁
            document.body.classList.add(Runner.classes.INVERTED, false);
            this.flashTimer = 0;
            this.flashIterations = 0;
        } else {
            // 切换闪烁状态
            this.flashIterations = document.body.classList.toggle(
                Runner.classes.INVERTED,
                this.flashIterations
            );
        }
    };

    /**
     * 检测是否为高DPI屏幕
     * @returns {boolean}
     */
    Runner.prototype.isHidpi = function() {
        return window.devicePixelRatio > 1;
    };

    /**
     * 更新画布的缩放比例（高清屏适配）
     * @param {HTMLCanvasElement} canvas - 画布元素
     * @param {number} optWidth - 可选宽度
     * @param {number} optHeight - 可选高度
     * @returns {boolean} 是否进行了缩放
     */
    Runner.updateCanvasScaling = function(canvas, optWidth, optHeight) {
        var context = canvas.getContext('2d');
        var devicePixelRatio = Math.floor(window.devicePixelRatio) || 1;
        var backingStoreRatio = Math.floor(context.webkitBackingStorePixelRatio) || 1;
        var ratio = devicePixelRatio / backingStoreRatio;

        // 如果像素比不匹配则需要缩放
        if (devicePixelRatio !== backingStoreRatio) {
            var newWidth = optWidth || canvas.width;
            var newHeight = optHeight || canvas.height;

            // 调整canvas物理像素
            canvas.width = newWidth * ratio;
            canvas.height = newHeight * ratio;
            // 保持CSS显示尺寸不变
            canvas.style.width = newWidth + 'px';
            canvas.style.height = newHeight + 'px';

            // 缩放绘图上下文
            context.scale(ratio, ratio);
            return true;
        }

        // 不做缩放时也要修正CSS尺寸
        if (devicePixelRatio === 1) {
            canvas.style.width = canvas.width + 'px';
            canvas.style.height = canvas.height + 'px';
        }
        return false;
    };

    // ==================== Trex（恐龙角色） ====================

    /**
     * 恐龙角色配置
     */
    Trex.config = {
        DROP_VELOCITY: -5,         // 下落速度
        GRAVITY: 0.6,              // 重力加速度
        HEIGHT: 47,                // 恐龙高度（像素）
        HEIGHT_DUCK: 25,           // 蹲下时的高度
        INIITAL_JUMP_VELOCITY: -10,// 初始跳跃速度（负值=向上）
        INTRO_DURATION: 1500,      // 开场动画时长
        MAX_JUMP_HEIGHT: 30,       // 最大跳跃高度
        MIN_JUMP_HEIGHT: 30,       // 最小跳跃高度
        SPEED_DROP_COEFFICIENT: 3, // 加速下落系数
        SPRITE_WIDTH: 262,         // 精灵宽度
        START_X_POS: 50,           // 起始X位置
        WIDTH: 44,                 // 恐龙宽度
        WIDTH_DUCK: 59,            // 蹲下时的宽度
    };

    /**
     * 恐龙精灵动画帧定义
     * 不同状态下使用不同的帧序列
     */
    Trex.animFrames = {
        WAITING: {
            frames: [44, 0],           // 等待动画帧（眨眼）
            msPerFrame: 1000 / 3       // 每帧间隔
        },
        RUNNING: {
            frames: [88, 132],         // 跑步动画帧（两帧交替）
            msPerFrame: 1000 / 12      // 每帧间隔
        },
        CRASHED: {
            frames: [220],             // 撞到障碍物的帧
            msPerFrame: 1000 / 60      // 每帧间隔
        },
        JUMPING: {
            frames: [0],               // 跳跃帧
            msPerFrame: 1000 / 60      // 每帧间隔
        },
        DUCKING: {
            frames: [264, 323],        // 蹲下动画帧
            msPerFrame: 1000 / 8       // 每帧间隔
        },
    };

    /**
     * 恐龙碰撞盒子定义（相对于恐龙位置）
     */
    Trex.collisionBoxes = {
        // 跑步状态的碰撞盒
        RUNNING: [
            new CollisionBox(22, 0, 17, 16),      // 头部
            new CollisionBox(1, 18, 30, 9),        // 身体上部
            new CollisionBox(10, 35, 14, 8),       // 身体中部
            new CollisionBox(1, 24, 29, 5),        // 身体
            new CollisionBox(5, 30, 21, 4),        // 身体下部
            new CollisionBox(9, 34, 15, 4),        // 腿部
        ],
        // 蹲下状态的碰撞盒
        DUCKING: [
            new CollisionBox(1, 18, 55, 25),       // 蹲下的整个身体
        ],
    };

    /**
     * 恐龙状态枚举
     */
    Trex.status = {
        CRASHED: 'CRASHED',     // 撞到障碍物
        DUCKING: 'DUCKING',     // 蹲下
        JUMPING: 'JUMPING',     // 跳跃中
        RUNNING: 'RUNNING',     // 跑步中
        WAITING: 'WAITING',     // 等待开始
    };

    /**
     * 更新间隔（随机眨眼）
     */
    Trex.BLINK_TIMING = 7000; // 每7秒眨眼一次

    /**
     * Trex 构造函数
     * @param {HTMLCanvasElement} canvas - 游戏画布
     * @param {Object} spritePos - 精灵图位置信息
     */
    function Trex(canvas, spritePos) {
        this.canvas = canvas;
        this.canvasCtx = canvas.getContext('2d');

        // 精灵图位置
        this.spritePos = spritePos;

        // 位置
        this.xPos = 0;
        this.yPos = 0;

        // 跳跃相关
        this.jumpVelocity = 0;      // 当前跳跃速度
        this.reachedMinHeight = false; // 是否达到最低跳跃高度
        this.speedDrop = false;     // 是否加速下落
        this.jumping = false;       // 是否正在跳跃
        this.ducking = false;       // 是否正在蹲下

        // 动画
        this.status = Trex.status.WAITING; // 初始状态
        this.currentAnimFrames = [];       // 当前动画帧序列
        this.animStartTime = 0;            // 动画起始时间
        this.timer = 0;                   // 动画计时器
        this.msPerFrame = 1000 / 60;       // 每帧毫秒数
        this.config = Trex.config;         // 配置

        // 地面Y坐标（计算得出）
        this.groundYPos = DEFAULT_DIMENSIONS.HEIGHT - this.config.HEIGHT - DEFAULT_CONFIG.BOTTOM_PAD;
        this.yPos = this.groundYPos;       // 初始Y位置
        this.minJumpHeight = this.groundYPos - this.config.MIN_JUMP_HEIGHT;

        // 绘制
        this.draw(0, 0);

        // 将状态设为等待
        this.update(0, Trex.status.WAITING);
    }

    /**
     * 设置跳跃速度
     * @param {number} speed - 当前游戏速度
     */
    Trex.prototype.setJumpVelocity = function(speed) {
        this.config.INIITAL_JUMP_VELOCITY = -speed;
        this.config.DROP_VELOCITY = -speed / 2;
    };

    /**
     * 主更新方法
     * @param {number} deltaTime - 时间增量
     * @param {string} optStatus - 可选的状态覆盖
     */
    Trex.prototype.update = function(deltaTime, optStatus) {
        this.timer += deltaTime;

        // 更新状态
        if (optStatus) {
            this.status = optStatus;
            this.currentFrame = 0;
            this.msPerFrame = Trex.animFrames[optStatus].msPerFrame;
            this.currentAnimFrames = Trex.animFrames[optStatus].frames;

            // 如果在等待状态，记录动画开始时间并生成随机眨眼间隔
            if (optStatus == Trex.status.WAITING) {
                this.animStartTime = getTimeStamp();
                this.setRandomBlinkDelay();
            }
        }

        // 处理开场动画
        if (this.playingIntro && this.xPos < this.config.START_X_POS) {
            this.xPos += Math.floor(this.config.START_X_POS / this.config.INTRO_DURATION * deltaTime);
        }

        // 等待状态的眨眼动画
        if (this.status == Trex.status.WAITING) {
            this.blink(getTimeStamp());
        } else {
            // 根据时间切换动画帧
            this.draw(this.currentAnimFrames[this.currentFrame], 0);
        }

        // 帧计时器
        if (this.timer >= this.msPerFrame) {
            // 切换到下一帧
            this.currentFrame = this.currentFrame == this.currentAnimFrames.length - 1 ? 0 : this.currentFrame + 1;
            this.timer = 0;
        }

        // 快速下落时，当到达地面则停止快速下落
        if (this.speedDrop && this.yPos == this.groundYPos) {
            this.speedDrop = false;
            this.setDuck(true);
        }
    };

    /**
     * 绘制恐龙
     * @param {number} x - 精灵图X偏移
     * @param {number} y - 精灵图Y偏移
     */
    Trex.prototype.draw = function(x, y) {
        // 蹲下时使用不同的尺寸
        var sourceWidth = this.ducking && this.status != Trex.status.CRASHED ?
            this.config.WIDTH_DUCK : this.config.WIDTH;
        var sourceHeight = this.config.HEIGHT;

        x += this.spritePos.x;
        y += this.spritePos.y;

        // 蹲下状态调整Y位置
        if (this.ducking && this.status != Trex.status.CRASHED) {
            this.canvasCtx.drawImage(
                Runner.imageSprite,
                x, y,
                this.config.WIDTH_DUCK, this.config.HEIGHT,
                this.xPos, this.yPos,
                this.config.WIDTH_DUCK, this.config.HEIGHT
            );
        } else {
            // 正常状态下如果蹲下了需要增加y坐标
            if (this.ducking && this.status == Trex.status.CRASHED) {
                this.xPos++;
            }
            this.canvasCtx.drawImage(
                Runner.imageSprite,
                x, y,
                this.config.WIDTH, this.config.HEIGHT,
                this.xPos, this.yPos,
                this.config.WIDTH, this.config.HEIGHT
            );
        }
    };

    /**
     * 生成随机眨眼间隔
     */
    Trex.prototype.setRandomBlinkDelay = function() {
        this.blinkDelay = Math.ceil(Math.random() * Trex.BLINK_TIMING);
    };

    /**
     * 眨眼动画
     * @param {number} time - 当前时间戳
     */
    Trex.prototype.blink = function(time) {
        var deltaTime = time - this.animStartTime;

        if (deltaTime >= this.blinkDelay) {
            // 到达眨眼时间，播放眨眼帧
            this.draw(this.currentAnimFrames[this.currentFrame], 0);

            // 第二帧后重置计时器
            if (this.currentFrame == 1) {
                this.setRandomBlinkDelay();
                this.animStartTime = time;
                this.blinkCount++;
            }
        }
    };

    /**
     * 开始跳跃
     * @param {number} speed - 当前游戏速度
     */
    Trex.prototype.startJump = function(speed) {
        if (!this.jumping) {
            // 切换到跳跃状态
            this.update(0, Trex.status.JUMPING);

            // 根据速度调整跳跃力度
            this.jumpVelocity = this.config.INIITAL_JUMP_VELOCITY - (speed / 10);
            this.jumping = true;
            this.reachedMinHeight = false;
            this.speedDrop = false;
        }
    };

    /**
     * 结束跳跃（松键时调用，实现可变跳跃高度）
     */
    Trex.prototype.endJump = function() {
        // 只有在达到最小跳跃高度后才允许提前下落
        if (this.reachedMinHeight && this.jumpVelocity < this.config.DROP_VELOCITY) {
            this.jumpVelocity = this.config.DROP_VELOCITY;
        }
    };

    /**
     * 跳跃物理更新
     * @param {number} deltaTime - 时间增量
     */
    Trex.prototype.updateJump = function(deltaTime) {
        var msPerFrame = Trex.animFrames[this.status].msPerFrame;
        var framesElapsed = deltaTime / msPerFrame;

        // 加速下落模式
        if (this.speedDrop) {
            this.yPos += Math.floor(this.jumpVelocity * this.config.SPEED_DROP_COEFFICIENT * framesElapsed);
        } else {
            this.yPos += Math.floor(this.jumpVelocity * framesElapsed);
        }

        // 应用重力
        this.jumpVelocity += this.config.GRAVITY * framesElapsed;

        // 检测是否达到最小跳跃高度
        if (this.yPos < this.minJumpHeight || this.speedDrop) {
            this.reachedMinHeight = true;
        }

        // 快速下落时强制设置velocity
        if (this.yPos < this.config.MAX_JUMP_HEIGHT || this.speedDrop) {
            this.endJump();
        }

        // 落地检测
        if (this.yPos > this.groundYPos) {
            this.reset();    // 重置到跑步状态
            this.jumpCount++; // 增加跳跃计数
        }

        this.update(deltaTime);
    };

    /**
     * 加速下落（在空中按下蹲键触发）
     */
    Trex.prototype.setSpeedDrop = function() {
        this.speedDrop = true;
        this.jumpVelocity = 1;
    };

    /**
     * 设置蹲下状态
     * @param {boolean} isDucking - 是否蹲下
     */
    Trex.prototype.setDuck = function(isDucking) {
        if (isDucking && this.status != Trex.status.DUCKING) {
            // 开始蹲下
            this.update(0, Trex.status.DUCKING);
            this.ducking = true;
        } else if (this.status == Trex.status.DUCKING) {
            // 停止蹲下
            this.update(0, Trex.status.RUNNING);
            this.ducking = false;
        }
    };

    /**
     * 重置恐龙状态
     */
    Trex.prototype.reset = function() {
        this.yPos = this.groundYPos;
        this.jumpVelocity = 0;
        this.jumping = false;
        this.ducking = false;
        this.update(0, Trex.status.RUNNING);
        this.speedDrop = false;
        this.jumpCount = 0;
    };

    // ==================== Obstacle（障碍物） ====================

    /**
     * 障碍物类型定义
     * 每种类型包含：精灵图偏移、尺寸、碰撞盒、动画帧等
     */
    var OBSTACLE_TYPES = [
        {
            type: 'CACTUS_SMALL',       // 小型仙人掌
            width: 17,                   // 宽度
            height: 35,                  // 高度
            yPos: 105,                   // 地面偏移
            multipleSpeed: 4,            // 速度倍数
            minGap: 120,                // 最小间隙
            minSpeed: 0,                // 最低速度要求
            collisionBoxes: [
                new CollisionBox(0, 7, 5, 27),
                new CollisionBox(4, 0, 6, 34),
                new CollisionBox(10, 4, 7, 14),
            ],
        },
        {
            type: 'CACTUS_LARGE',       // 大型仙人掌
            width: 25,
            height: 50,
            yPos: 90,
            multipleSpeed: 7,
            minGap: 120,
            minSpeed: 0,
            collisionBoxes: [
                new CollisionBox(0, 12, 7, 38),
                new CollisionBox(8, 0, 7, 49),
                new CollisionBox(13, 10, 10, 38),
            ],
        },
        {
            type: 'PTERODACTYL',        // 翼龙（飞行障碍物）
            width: 46,
            height: 40,
            yPos: [100, 75, 50],       // 三种飞行高度
            yPosMobile: [100, 50],      // 移动端的飞行高度
            multipleSpeed: 999,         // 不会成组出现
            minGap: 8.5,
            minSpeed: 150,
            collisionBoxes: [
                new CollisionBox(15, 15, 16, 5),
                new CollisionBox(18, 21, 24, 6),
                new CollisionBox(2, 14, 4, 3),
                new CollisionBox(6, 10, 4, 7),
                new CollisionBox(10, 8, 6, 9),
            ],
            numFrames: 2,               // 两帧动画（翅膀扇动）
            frameRate: 1000 / 6,        // 帧率
            speedOffset: 0.8,           // 速度偏移系数
        },
    ];

    /**
     * 障碍物构造函数
     * @param {HTMLCanvasElement} canvas - 画布
     * @param {Object} type - 障碍物类型配置
     * @param {Object} spriteImgPos - 精灵图位置
     * @param {Object} dimensions - 画布尺寸
     * @param {number} gapCoefficient - 间隙系数
     * @param {number} speed - 当前游戏速度
     * @param {number} optXOffset - 可选的X偏移
     */
    function Obstacle(canvas, type, spriteImgPos, dimensions, gapCoefficient, speed, optXOffset) {
        this.canvas = canvas;
        this.canvasCtx = canvas.getContext('2d');

        // 类型配置
        this.typeConfig = type;
        this.gapCoefficient = gapCoefficient;
        // 随机大小（1-3个仙人掌连在一起）
        this.size = getRandomNum(1, Obstacle.MAX_OBSTACLE_LENGTH);
        this.dimensions = dimensions;
        this.xOffset = optXOffset || 0;

        // 从精灵图中获取对应图片
        this.imageSprite = type.type;
        this.spritePos = spriteImgPos;

        // 初始化位置和尺寸
        this.init(dimensions.WIDTH);
    }

    /** 最大障碍物长度 */
    Obstacle.MAX_OBSTACLE_LENGTH = 3;

    /**
     * 初始化障碍物
     * @param {number} canvasWidth - 画布宽度
     */
    Obstacle.prototype.init = function(canvasWidth) {
        // 创建碰撞盒子（深拷贝）
        this.cloneCollisionBoxes();

        // 限制障碍物大小
        if (this.size > 1 && this.typeConfig.multipleSpeed > canvasWidth) {
            this.size = 1;
        }

        // 计算总宽度
        this.width = this.typeConfig.width * this.size;

        // 设置Y位置：随机选择（如果是翼龙有多种高度）
        if (Array.isArray(this.typeConfig.yPos)) {
            var yPosConfig = isMobile ? this.typeConfig.yPosMobile : this.typeConfig.yPos;
            this.yPos = yPosConfig[getRandomNum(0, yPosConfig.length - 1)];
        } else {
            this.yPos = this.typeConfig.yPos;
        }

        // 绘制
        this.draw();

        // 如果有多个障碍物连接，调整碰撞盒
        if (this.size > 1) {
            // 调整中间段的碰撞盒宽度
            this.collisionBoxes[1].width = this.width - this.collisionBoxes[0].width - this.collisionBoxes[2].width;
            // 调整最后一段的X位置
            this.collisionBoxes[2].x = this.width - this.collisionBoxes[2].width;
        }

        // 随机决定是否翻转（翼龙飞行的方向偏移）
        if (this.typeConfig.speedOffset) {
            this.speedOffset = Math.random() > 0.5 ? this.typeConfig.speedOffset : -this.typeConfig.speedOffset;
        }

        // 计算间隙
        this.gap = this.getGap(this.gapCoefficient, canvasWidth);
    };

    /**
     * 绘制障碍物
     */
    Obstacle.prototype.draw = function() {
        var sourceWidth = this.typeConfig.width;
        var sourceHeight = this.typeConfig.height;

        // 多个障碍物连接时的X坐标计算
        var xOffset = sourceWidth * this.size * 0.5 * (this.size - 1) + this.spritePos.x;
        if (this.size > 1) {
            xOffset += sourceWidth * this.doubleSize;
        }

        this.canvasCtx.drawImage(
            Runner.imageSprite,
            xOffset, this.spritePos.y,
            sourceWidth * this.size, sourceHeight,
            this.xPos, this.yPos,
            this.typeConfig.width * this.size, this.typeConfig.height
        );
    };

    /**
     * 更新障碍物位置
     * @param {number} deltaTime - 时间增量
     * @param {number} speed - 当前游戏速度
     */
    Obstacle.prototype.update = function(deltaTime, speed) {
        if (!this.followingObstacleCreated) {
            // 处理翼龙的速度偏移
            if (this.typeConfig.speedOffset) {
                speed += this.speedOffset;
            }

            // 向左移动
            this.xPos -= Math.floor(60 * speed / 1000 * deltaTime);

            // 翼龙动画帧更新
            if (this.typeConfig.numFrames) {
                this.timer += deltaTime;
                if (this.timer >= this.typeConfig.frameRate) {
                    // 切换翅膀帧
                    this.currentFrame = this.currentFrame == this.typeConfig.numFrames - 1 ? 0 : this.currentFrame + 1;
                    this.timer = 0;
                }
            }

            this.draw();

            // 检测是否已移出屏幕
            if (!this.isVisible()) {
                this.followingObstacleCreated = true;
            }
        }
    };

    /**
     * 计算障碍物之间的间隙
     * @param {number} gapCoefficient - 间隙系数
     * @param {number} canvasWidth - 画布宽度
     * @returns {number} 间隙像素值
     */
    Obstacle.prototype.getGap = function(gapCoefficient, canvasWidth) {
        var baseGap = Math.round(this.width * canvasWidth + this.typeConfig.minGap * gapCoefficient);
        return getRandomNum(baseGap, Math.round(baseGap * Obstacle.MAX_GAP_COEFFICIENT));
    };

    /** 最大间隙系数 */
    Obstacle.MAX_GAP_COEFFICIENT = 1.5;

    /**
     * 判断障碍物是否还在屏幕内可见
     * @returns {boolean}
     */
    Obstacle.prototype.isVisible = function() {
        return this.xPos + this.width > 0;
    };

    /**
     * 深拷贝碰撞盒子定义
     */
    Obstacle.prototype.cloneCollisionBoxes = function() {
        var source = this.typeConfig.collisionBoxes;
        this.collisionBoxes = [];
        for (var i = source.length - 1; i >= 0; i--) {
            this.collisionBoxes[i] = new CollisionBox(
                source[i].x, source[i].y,
                source[i].width, source[i].height
            );
        }
    };

    // ==================== Horizon（地平线管理器） ====================

    /**
     * 地平线默认配置
     */
    Horizon.config = {
        BG_CLOUD_SPEED: 0.2,        // 背景云朵速度
        BUMPY_THRESHOLD: 0.3,       // 颠簸阈值
        CLOUD_FREQUENCY: 0.5,       // 云朵出现频率
        HORIZON_HEIGHT: 16,         // 地平线高度
        MAX_CLOUD_GAP: 400,         // 最大云朵间隙
        MIN_CLOUD_GAP: 100,         // 最小云朵间隙
        MAX_SKY_LEVEL: 30,          // 最大天空高度
        MIN_SKY_LEVEL: 71,          // 最小天空高度（值越大越靠下）
        NIGHT_MODE_ALPHA: 0.3,      // 夜间模式透明度
        SPEED: 6,                   // 基础速度
        SPEED_DROP_COEFFICIENT: 3,  // 速度下降系数
    };

    /**
     * 地平线状态枚举
     */
    Horizon.status = {
        CRASHED: 'CRASHED',
        DUCKING: 'DUCKING',
        JUMPING: 'JUMPING',
        RUNNING: 'RUNNING',
        WAITING: 'WAITING',
    };

    /**
     * 地平线动画帧
     */
    Horizon.animFrames = {
        WAITING: { frames: [44, 0],    msPerFrame: 1000 / 3 },
        RUNNING: { frames: [88, 132],  msPerFrame: 1000 / 12 },
        CRASHED: { frames: [220],      msPerFrame: 1000 / 60 },
        JUMPING: { frames: [0],        msPerFrame: 1000 / 60 },
        DUCKING: { frames: [264, 323], msPerFrame: 1000 / 8 },
    };

    /**
     * Horizon 构造函数 - 管理整个游戏场景
     * @param {HTMLCanvasElement} canvas - 画布
     * @param {Object} spritePos - 精灵图位置映射
     * @param {Object} dimensions - 画布尺寸
     * @param {number} gapCoefficient - 间隙系数
     */
    function Horizon(canvas, spritePos, dimensions, gapCoefficient) {
        this.canvas = canvas;
        this.canvasCtx = canvas.getContext('2d');

        // 精灵图位置信息
        this.spritePos = spritePos;

        // 画布尺寸（运行时可变）
        this.dimensions = dimensions;

        // 间隙系数
        this.gapCoefficient = gapCoefficient;

        // 障碍物管理
        this.obstacles = [];                // 活跃障碍物列表
        this.obstacleHistory = [];          // 最近出现的障碍物类型（用于避免重复）

        // 背景元素
        this.horizonLine = null;            // 地平线
        this.clouds = [];                   // 云朵列表
        this.cloudSpeed = this.config.BG_CLOUD_SPEED;

        // 夜间模式
        this.nightMode = null;              // 夜间模式覆盖层
        this.inverted = false;              // 是否处于倒置模式（夜间）

        // X位置（用于滚动背景）
        this.xPos = [0, 0];

        // 初始化
        this.init();
    }

    /**
     * 初始化地平线场景
     */
    Horizon.prototype.init = function() {
        // 添加地平线（两条以实现无缝滚动）
        this.addCloud();
        this.horizonLine = new HorizonLine(this.canvas, this.spritePos.HORIZON);
        this.nightMode = new NightMode(this.canvas, this.spritePos.MOON, this.dimensions.WIDTH);
    };

    /**
     * 主更新方法
     * @param {number} deltaTime - 时间增量
     * @param {number} speed - 当前速度
     * @param {boolean} showInverted - 是否显示夜间模式
     */
    Horizon.prototype.update = function(deltaTime, speed, showInverted) {
        this.timer += deltaTime;

        // 更新夜间模式
        this.nightMode.update(deltaTime, speed);

        // 更新云朵
        this.updateClouds(deltaTime, speed);

        if (showInverted) {
            // 如果是倒置模式，更新地平线
            this.horizonLine.update(deltaTime, speed);
        }

        // 更新障碍物
        this.updateObstacles(deltaTime, speed);

        // 随机生成新障碍物
        if (this.obstacles.length > 0) {
            var lastObstacle = this.obstacles[this.obstacles.length - 1];
            if (lastObstacle && !lastObstacle.followingObstacleCreated &&
                lastObstacle.isVisible() &&
                lastObstacle.xPos + lastObstacle.width + lastObstacle.gap < this.dimensions.WIDTH) {
                this.addNewObstacle(speed, deltaTime);
                lastObstacle.followingObstacleCreated = true;
            }
        } else {
            // 没有障碍物时直接创建
            this.addNewObstacle(speed);
        }

        // 清理已移出屏幕的障碍物
        this.removeFirstObstacle();
    };

    /**
     * 更新云朵位置
     * @param {number} deltaTime
     * @param {number} speed
     */
    Horizon.prototype.updateClouds = function(deltaTime, speed) {
        var cloudSpeed = this.cloudSpeed / 1000 * deltaTime * speed;
        var numClouds = this.clouds.length;

        if (numClouds) {
            for (var i = numClouds - 1; i >= 0; i--) {
                this.clouds[i].update(cloudSpeed);
            }

            // 移除移出屏幕的云朵
            this.clouds = this.clouds.filter(function(cloud) {
                return cloud.isVisible();
            });
        } else {
            // 没有云朵时添加一个新云朵
            this.addCloud();
        }
    };

    /**
     * 添加新障碍物
     * @param {number} speed
     * @param {number} deltaTime
     */
    Horizon.prototype.addNewObstacle = function(speed, deltaTime) {
        // 从障碍物类型中随机选择
        var randomIndex = getRandomNum(0, OBSTACLE_TYPES.length - 1);
        var obstacleType = OBSTACLE_TYPES[randomIndex];

        // 检查是否重复
        if (this.duplicateObstacleCheck(obstacleType.type) ||
            (deltaTime && deltaTime < obstacleType.minSpeed)) {
            // 递归尝试其他类型
            this.addNewObstacle(speed);
            return;
        }

        // 创建新的障碍物
        var obstacleObj = new Obstacle(
            this.canvas,
            obstacleType,
            this.spritePos[obstacleType.type],
            this.dimensions,
            this.gapCoefficient,
            speed,
            obstacleType.width
        );

        this.obstacles.push(obstacleObj);
        this.obstacleHistory.push(obstacleType.type);

        // 限制历史记录长度
        if (this.obstacleHistory.length > 1) {
            this.obstacleHistory.shift();
        }
    };

    /**
     * 检查障碍物类型是否应该被排除（避免连续出现相同类型）
     * @param {string} type - 障碍物类型
     * @returns {boolean} 是否应该跳过
     */
    Horizon.prototype.duplicateObstacleCheck = function(type) {
        var duplicateCount = 0;
        for (var i = 0; i < this.obstacleHistory.length; i++) {
            duplicateCount = this.obstacleHistory[i] == type ? duplicateCount + 1 : 0;
        }
        return duplicateCount >= Runner.config.MAX_OBSTACLE_DUPLICATION;
    };

    /**
     * 移除已经退出屏幕的障碍物
     */
    Horizon.prototype.removeFirstObstacle = function() {
        if (this.obstacles.length > 0 && this.obstacles[0].xPos + this.obstacles[0].width < 0) {
            this.obstacles.shift();
        }
    };

    /**
     * 添加云朵
     */
    Horizon.prototype.addCloud = function() {
        this.clouds.push(new Cloud(this.canvas, this.spritePos.CLOUD, this.dimensions.WIDTH));
    };

    /**
     * 重置地平线（游戏重启时调用）
     */
    Horizon.prototype.reset = function() {
        this.obstacles = [];
        this.horizonLine.reset();
        this.nightMode.reset();
    };

    /**
     * 调整画布尺寸
     * @param {number} width - 新宽度
     * @param {number} height - 新高度
     */
    Horizon.prototype.updateDimensions = function(width, height) {
        this.canvas.width = width;
        this.canvas.height = height;
    };

    // ==================== HorizonLine（地平线/地面线条） ====================

    /**
     * 地平线配置
     */
    HorizonLine.dimensions = {
        WIDTH: 600,       // 默认宽度
        HEIGHT: 12,       // 高度
        YPOS: 127,        // Y坐标位置
    };

    /**
     * 地平线构造函数
     * @param {HTMLCanvasElement} canvas
     * @param {Object} spritePos - 精灵图位置
     */
    function HorizonLine(canvas, spritePos) {
        this.canvas = canvas;
        this.canvasCtx = canvas.getContext('2d');
        this.spritePos = spritePos;

        // 地平线尺寸
        this.dimensions = HorizonLine.dimensions;
        // X坐标（两条地平线实现无缝滚动）
        this.xPos = [0, HorizonLine.dimensions.WIDTH];
        this.yPos = this.spritePos.y;

        // 随机初始偏移
        this.bumpThreshold = 0.5;

        // 初始化
        this.setSourceDimensions();
        this.draw();
    }

    /**
     * 设置源图片尺寸
     */
    HorizonLine.prototype.setSourceDimensions = function() {
        // 从精灵图配置中获取尺寸
        for (var key in HorizonLine.dimensions) {
            if (key === 'YPOS') {
                this.yPos = HorizonLine.dimensions[key];
            } else {
                // 复制宽高
                this.dimensions[key] = HorizonLine.dimensions[key];
            }
        }

        // 两条地平线的X坐标
        this.xPos = [0, HorizonLine.dimensions.WIDTH];
        this.sourceXPos = [this.getRandomXPos(), this.getRandomXPos()];
    };

    /**
     * 获取随机的源X偏移
     * @returns {number}
     */
    HorizonLine.prototype.getRandomXPos = function() {
        return Math.random() > this.bumpThreshold ? this.dimensions.WIDTH : 0;
    };

    /**
     * 绘制地平线
     */
    HorizonLine.prototype.draw = function() {
        this.canvasCtx.drawImage(
            Runner.imageSprite,
            this.sourceXPos[0], this.spritePos.y,
            this.dimensions.WIDTH, this.dimensions.HEIGHT,
            this.xPos[0], this.yPos,
            this.dimensions.WIDTH, this.dimensions.HEIGHT
        );
        this.canvasCtx.drawImage(
            Runner.imageSprite,
            this.sourceXPos[1], this.spritePos.y,
            this.dimensions.WIDTH, this.dimensions.HEIGHT,
            this.xPos[1], this.yPos,
            this.dimensions.WIDTH, this.dimensions.HEIGHT
        );
    };

    /**
     * 更新地平线位置（实现无缝滚动）
     * @param {number} deltaTime
     * @param {number} speed
     */
    HorizonLine.prototype.updateXPos = function(deltaTime, speed) {
        // 两条地平线都向左移动
        var line1 = 0;
        var line2 = 1;
        var distance = Math.floor(60 * speed / 1000 * deltaTime);

        this.xPos[line1] -= distance;
        this.xPos[line2] = this.xPos[line1] + this.dimensions.WIDTH;

        // 当第一条线完全移出屏幕时，重新定位
        if (this.xPos[line1] <= -this.dimensions.WIDTH) {
            this.xPos[line1] += 2 * this.dimensions.WIDTH;
            this.xPos[line2] = this.xPos[line1] - this.dimensions.WIDTH;
            this.sourceXPos[line1] = this.getRandomXPos() + this.spritePos.x;
        }

        this.draw();
    };

    /**
     * 重置
     */
    HorizonLine.prototype.reset = function() {
        this.xPos = [0, HorizonLine.dimensions.WIDTH];
        this.sourceXPos = [this.getRandomXPos(), this.getRandomXPos()];
    };

    // ==================== Cloud（云朵） ====================

    /**
     * 云朵配置
     */
    Cloud.config = {
        HEIGHT: 14,              // 高度
        MAX_CLOUD_GAP: 400,      // 最大间隙
        MAX_SKY_LEVEL: 30,       // 最大天空高度（Y坐标最小值）
        MIN_CLOUD_GAP: 100,      // 最小间隙
        MIN_SKY_LEVEL: 71,       // 最小天空高度（Y坐标最大值）
        WIDTH: 46,               // 宽度
    };

    /**
     * 云朵构造函数
     * @param {HTMLCanvasElement} canvas
     * @param {Object} spritePos
     * @param {number} containerWidth - 容器宽度
     */
    function Cloud(canvas, spritePos, containerWidth) {
        this.canvas = canvas;
        this.canvasCtx = canvas.getContext('2d');
        this.spritePos = spritePos;
        this.containerWidth = containerWidth;

        // 随机起始X位置（屏幕右边缘外）
        this.xPos = containerWidth;
        // 随机Y位置（天空高度范围）
        this.yPos = getRandomNum(Cloud.config.MAX_SKY_LEVEL, Cloud.config.MIN_SKY_LEVEL);

        // 随机大小（但是实际尺寸不变，用于间隙计算）
        this.size = 0;

        this.draw();
    }

    /**
     * 绘制云朵
     */
    Cloud.prototype.draw = function() {
        this.canvasCtx.drawImage(
            Runner.imageSprite,
            this.spritePos.x, this.spritePos.y,
            Cloud.config.WIDTH, Cloud.config.HEIGHT,
            this.xPos, this.yPos,
            Cloud.config.WIDTH, Cloud.config.HEIGHT
        );
    };

    /**
     * 更新云朵位置
     * @param {number} speed - 移动速度（像素/帧）
     */
    Cloud.prototype.update = function(speed) {
        if (!this.isVisible()) {
            // 移出屏幕则重新定位到右侧
            this.xPos = this.containerWidth + getRandomNum(Cloud.config.MIN_CLOUD_GAP, Cloud.config.MAX_CLOUD_GAP);
            this.yPos = getRandomNum(Cloud.config.MAX_SKY_LEVEL, Cloud.config.MIN_SKY_LEVEL);
        }

        // 向左移动
        this.xPos -= Math.ceil(speed);
        this.draw();
    };

    /**
     * 判断云朵是否可见
     * @returns {boolean}
     */
    Cloud.prototype.isVisible = function() {
        return this.xPos + Cloud.config.WIDTH > 0;
    };

    // ==================== NightMode（夜间模式/月亮） ====================

    /**
     * 夜间模式配置
     */
    NightMode.config = {
        FADE_SPEED: 0.035,        // 淡入淡出速度
        HEIGHT: 40,               // 月亮高度
        MOON_SPEED: 0.25,         // 月亮移动速度
        NUM_STARS: 2,             // 星星数量
        STAR_SIZE: 9,             // 星星大小
        STAR_SPEED: 0.3,          // 星星移动速度
        STAR_MAX_Y: 70,           // 星星最大Y坐标
        WIDTH: 20,                // 月亮宽度
    };

    /**
     * 星星的Y坐标（离地平线的偏移）
     */
    NightMode.starYPositions = [115, 120, 100, 60, 40, 20, 0];

    /**
     * NightMode 构造函数
     * @param {HTMLCanvasElement} canvas
     * @param {Object} spritePos - 月亮精灵图位置
     * @param {number} containerWidth
     */
    function NightMode(canvas, spritePos, containerWidth) {
        this.canvas = canvas;
        this.canvasCtx = canvas.getContext('2d');
        this.spritePos = spritePos;
        this.containerWidth = containerWidth;

        // 月亮位置
        this.xPos = containerWidth - 50;  // 初始在屏幕右侧
        this.yPos = 30;
        this.opacity = 0;                 // 透明度（控制淡入淡出）
        this.active = false;              // 是否处于夜间模式

        // 星星
        this.stars = [];
        this.placeStars();                // 初始布置星星

        this.draw();
    }

    /**
     * 更新夜间模式状态
     * @param {number} activated - 是否激活
     */
    NightMode.prototype.update = function(activated) {
        // 控制透明度渐变
        if (activated && this.opacity === 0) {
            // 激活夜间模式：渐显
            this.active = true;
            this.opacity += NightMode.config.FADE_SPEED;
        } else if (this.active && this.opacity > 0) {
            // 停用夜间模式：渐隐
            this.opacity -= NightMode.config.FADE_SPEED;
        }

        if (this.opacity > 0) {
            // 更新月亮位置
            this.xPos = this.updateXPos(this.xPos, NightMode.config.MOON_SPEED);

            // 更新星星位置
            if (this.active) {
                for (var i = 0; i < NightMode.config.NUM_STARS; i++) {
                    this.stars[i].x = this.updateXPos(this.stars[i].x, NightMode.config.STAR_SPEED);
                }
            }
            this.draw();
        } else {
            this.opacity = 0;
            this.placeStars(); // 重置星星
        }
        this.active = true;
    };

    /**
     * 更新X坐标（循环滚动）
     * @param {number} xPos - 当前X坐标
     * @param {number} speed - 移动速度
     * @returns {number} 新的X坐标
     */
    NightMode.prototype.updateXPos = function(xPos, speed) {
        xPos -= speed;
        // 移出屏幕后重新出现在右侧
        if (xPos < -NightMode.config.WIDTH) {
            xPos = this.containerWidth;
        }
        return xPos;
    };

    /**
     * 绘制月亮和星星
     */
    NightMode.prototype.draw = function() {
        var moonWidth = NightMode.config.WIDTH;
        var moonHeight = NightMode.config.HEIGHT;
        var moonX = this.spritePos.x + (3 == this.stars.length ? 2 * NightMode.config.WIDTH : NightMode.config.WIDTH);
        var starSize = NightMode.config.STAR_SIZE;

        this.canvasCtx.save();
        this.canvasCtx.globalAlpha = this.opacity;

        // 绘制星星
        if (this.active) {
            for (var i = 0; i < NightMode.config.NUM_STARS; i++) {
                this.canvasCtx.drawImage(
                    Runner.imageSprite,
                    this.stars[i].sourceX, this.stars[i].sourceY,
                    starSize, starSize,
                    Math.round(this.stars[i].x), this.stars[i].y,
                    NightMode.config.STAR_SIZE, NightMode.config.STAR_SIZE
                );
            }
        }

        // 绘制月亮
        this.canvasCtx.drawImage(
            Runner.imageSprite,
            moonX, this.spritePos.y,
            moonWidth, moonHeight,
            Math.round(this.xPos), this.yPos,
            moonWidth, NightMode.config.HEIGHT
        );

        this.canvasCtx.globalAlpha = 1;
        this.canvasCtx.restore();
    };

    /**
     * 随机布置星星位置
     */
    NightMode.prototype.placeStars = function() {
        var segmentSize = Math.round(this.containerWidth / NightMode.config.NUM_STARS);

        for (var i = 0; i < NightMode.config.NUM_STARS; i++) {
            this.stars[i] = {};
            this.stars[i].x = getRandomNum(segmentSize * i, segmentSize * (i + 1));
            this.stars[i].y = getRandomNum(0, NightMode.config.STAR_MAX_Y);
            this.stars[i].sourceX = NightMode.starYPositions[i] + NightMode.config.STAR_SIZE * i;
        }
    };

    /**
     * 重置夜间模式
     */
    NightMode.prototype.reset = function() {
        this.opacity = 0;
        this.active = false;
        this.placeStars();
    };

    // ==================== DistanceMeter（距离/分数显示） ====================

    /**
     * 距离计量器配置
     */
    DistanceMeter.dimensions = {
        WIDTH: 10,       // 每个数字宽度
        HEIGHT: 13,      // 数字高度
        DEST_WIDTH: 11,  // 目标宽度
    };

    /**
     * 数字精灵图中的Y偏移（对应数字0-9）
     */
    DistanceMeter.yPos = [0, 13, 27, 40, 53, 67, 80, 93, 107, 120];

    /**
     * 距离计量器配置
     */
    DistanceMeter.config = {
        MAX_DISTANCE_UNITS: 5,          // 最大显示位数
        ACHIEVEMENT_DISTANCE: 100,      // 成就触发距离
        COEFFICIENT: 0.025,            // 距离转换系数
        FLASH_ITERATIONS: 3,           // 闪烁次数
        CLEAR_TIME: 250,               // 闪烁间隔
    };

    /**
     * DistanceMeter 构造函数 - 显示跑步距离/分数
     * @param {HTMLCanvasElement} canvas
     * @param {Object} spritePos - 文字精灵图位置
     * @param {number} containerWidth - 容器宽度
     */
    function DistanceMeter(canvas, spritePos, containerWidth) {
        this.canvas = canvas;
        this.canvasCtx = canvas.getContext('2d');
        this.imageSprite = Runner.imageSprite;

        // 精灵图位置
        this.spritePos = spritePos;

        // X位置（根据容器宽度计算）
        this.x = 0;
        this.y = 5;

        // 高分闪烁效果
        this.highScoreFlash = [
            ['10', '11', ''], // "HI" 文字
        ];
        this.flashing = false;          // 是否正在闪烁
        this.defaultString = '';        // 默认显示的字符串

        // 状态
        this.maxScore = 0;
        this.timer = 0;
        this.blinkCount = 0;
        this.maxScoreUnits = containerWidth;

        // 初始化
        this.init(containerWidth);
    }

    /**
     * 初始化
     * @param {number} containerWidth
     */
    DistanceMeter.prototype.init = function(containerWidth) {
        var defaultStr = '';
        this.calcXPos(containerWidth);
        this.maxScore = this.maxScoreUnits;

        // 构建默认显示字符串（全0）
        for (var i = 0; i < this.maxScoreUnits; i++) {
            this.draw(i, 0);
            defaultStr += '0';
        }
        this.defaultString = parseInt(defaultStr, 10);
    };

    /**
     * 计算X显示位置（右对齐）
     * @param {number} containerWidth
     */
    DistanceMeter.prototype.calcXPos = function(containerWidth) {
        this.x = containerWidth - DistanceMeter.dimensions.DEST_WIDTH * (this.maxScoreUnits + 1);
    };

    /**
     * 绘制单个数字
     * @param {number} digitPos - 数字的位置索引（从右往左）
     * @param {number} value - 数字值（0-9, 10='H', 11='I'）
     * @param {boolean} isHighScore - 是否绘制高分标记
     */
    DistanceMeter.prototype.draw = function(digitPos, value, isHighScore) {
        var sourceWidth = DistanceMeter.dimensions.WIDTH;
        var sourceHeight = DistanceMeter.dimensions.HEIGHT;

        var targetX = digitPos * DistanceMeter.dimensions.DEST_WIDTH;
        var targetY = this.y;
        var sourceX = 0 + this.spritePos.x;
        var sourceY = 0 + this.spritePos.y;

        this.canvasCtx.save();

        if (isHighScore) {
            // 高分标记使用不同颜色
            this.canvasCtx.fillStyle = '#FF9800';
            this.canvasCtx.fillRect(this.x - 2 * this.maxScoreUnits * DistanceMeter.dimensions.WIDTH, this.y, 0, 0);
        } else {
            this.canvasCtx.fillStyle = '#757575';
        }

        this.canvasCtx.drawImage(
            Runner.imageSprite,
            sourceX, sourceY,
            sourceWidth, sourceHeight,
            targetX, targetY,
            DistanceMeter.dimensions.WIDTH, DistanceMeter.dimensions.HEIGHT
        );

        this.canvasCtx.restore();
    };

    /**
     * 将跑步距离转换为显示的数字
     * @param {number} distance - 实际距离
     * @returns {number} 显示值
     */
    DistanceMeter.prototype.getActualDistance = function(distance) {
        return distance ? Math.round(distance * this.config.COEFFICIENT) : 0;
    };

    /**
     * 更新距离显示
     * @param {number} deltaTime - 时间增量
     * @param {number} distance - 当前距离
     * @returns {boolean} 是否触发了闪烁
     */
    DistanceMeter.prototype.update = function(deltaTime, distance) {
        var paint = true;
        var playSound = false;

        if (!this.flashing) {
            // 非闪烁状态的闪烁计时器
            if (this.timer <= this.config.CLEAR_TIME) {
                this.blinkTimer += deltaTime;
                if (this.blinkTimer < this.config.FLASH_ITERATIONS) {
                    paint = false; // 闪烁间隙不绘制
                } else if (this.blinkTimer > 2 * this.config.FLASH_ITERATIONS) {
                    this.blinkTimer = 0;
                    this.blinkCount++;
                }
            } else {
                this.flashing = false;
                this.blinkTimer = this.blinkCount = 0;
            }
        } else {
            // 正常更新
            distance = this.getActualDistance(distance);

            // 位数不够时扩展
            if (distance > this.maxScore && this.maxScoreUnits == this.config.MAX_DISTANCE_UNITS) {
                this.maxScoreUnits++;
                this.defaultString = parseInt(this.defaultString + '9', 10);
            } else {
                this.digit = 0;
            }

            if (distance > 0) {
                // 每100分闪烁一次
                if (distance % this.config.ACHIEVEMENT_DISTANCE == 0) {
                    this.flashing = true;
                    this.blinkTimer = 0;
                    playSound = true;
                }
                // 更新显示的数字字符串
                this.digits = (this.defaultString + distance).substr(-this.maxScoreUnits).split('');
            } else {
                this.digits = this.defaultString.split('');
            }
        }

        if (paint) {
            // 绘制每个数字位
            for (var i = this.digits.length - 1; i >= 0; i--) {
                this.draw(i, parseInt(this.digits[i], 10));
            }
            this.drawHighScore();
        }
        return playSound;
    };

    /**
     * 绘制高分标记
     */
    DistanceMeter.prototype.drawHighScore = function() {
        this.canvasCtx.save();
        this.canvasCtx.globalAlpha = 0.8;
        for (var i = this.highScoreFlash.length - 1; i >= 0; i--) {
            this.draw(i, parseInt(this.highScoreFlash[i], 10), true);
        }
        this.canvasCtx.restore();
    };

    /**
     * 设置最高分闪烁显示
     * @param {number} distance - 最高分数
     */
    DistanceMeter.prototype.setHighScore = function(distance) {
        distance = this.getActualDistance(distance);
        var highScoreStr = (this.defaultString + distance).substr(-this.maxScoreUnits);
        this.highScoreFlash = ['10', '11', ''].concat(highScoreStr.split(''));
    };

    /**
     * 重置距离显示
     * @param {number} highScore - 最高分
     */
    DistanceMeter.prototype.reset = function(highScore) {
        this.update(0);
        this.flashing = false;
    };

    // ==================== GameOverPanel（游戏结束面板） ====================

    /**
     * 游戏结束面板配置
     */
    GameOverPanel.config = {
        HEIGHT: 14,              // 面板高度
        MAX_SCORE_UNITS: 5,      // 最大分数位数
        TEXT_WIDTH: 9,           // 文字宽度
        TEXT_HEIGHT: 11,         // 文字高度
        RESTART_WIDTH: 36,       // 重启按钮宽度
        RESTART_HEIGHT: 32,      // 重启按钮高度
    };

    /**
     * 数字到精灵图Y偏移的映射
     */
    GameOverPanel.digitYPositions = [130, 120, 100, 60, 40, 20, 0];

    /**
     * GameOverPanel 构造函数
     * @param {HTMLCanvasElement} canvas
     * @param {Object} textImgPos - 文字精灵图位置
     * @param {Object} restartImgPos - 重启按钮精灵图位置
     * @param {Object} dimensions - 画布尺寸
     */
    function GameOverPanel(canvas, textImgPos, restartImgPos, dimensions) {
        this.canvas = canvas;
        this.canvasCtx = canvas.getContext('2d');
        this.textImgPos = textImgPos;
        this.restartImgPos = restartImgPos;
        this.dimensions = dimensions;

        // 滚动效果
        this.scrollY = 0;
        this.scrollTarget = 0;

        // 分数显示
        this.score = 0;

        // 星星装饰
        this.stars = [];
        this.active = false;

        // 初始化
        this.placeStars();
    }

    /**
     * 更新游戏结束面板
     * @param {number} activated - 是否激活
     * @param {number} optScore - 最终分数
     */
    GameOverPanel.prototype.update = function(activated, optScore) {
        // 控制面板滑入动画
        if (activated && this.scrollY === 0) {
            this.scrollTarget = 1;
        } else if (this.scrollY > 0) {
            this.scrollTarget = this.easeOut(this.scrollTarget, GameOverPanel.config.SCROLL_SPEED);
        }

        if (this.scrollY > 0) {
            // 更新星星闪烁
            this.scrollY = this.easeOut(this.scrollY, GameOverPanel.config.SCROLL_FRICTION);
            if (this.active) {
                for (var i = 0; i < GameOverPanel.config.NUM_STARS; i++) {
                    this.stars[i].x = this.easeOut(this.stars[i].x, GameOverPanel.config.STAR_FRICTION);
                }
            }
            this.draw();
        } else {
            this.scrollY = 0;
            this.placeStars();
        }
        this.active = true;
    };

    /**
     * 缓动函数（用于平滑动画）
     * @param {number} value - 当前值
     * @param {number} target - 目标值
     * @returns {number} 缓动后的值
     */
    GameOverPanel.prototype.easeOut = function(value, target) {
        return value < -GameOverPanel.config.WIDTH ?
            this.dimensions.WIDTH : value - target;
    };

    /**
     * 绘制游戏结束面板
     */
    GameOverPanel.prototype.draw = function() {
        var textWidth = GameOverPanel.config.TEXT_WIDTH;
        var textHeight = GameOverPanel.config.TEXT_HEIGHT;
        var textX = this.textImgPos.x + (3 == this.stars.length ? 2 * textWidth : textWidth);
        var starSize = 9;

        this.canvasCtx.save();
        this.canvasCtx.globalAlpha = this.scrollY;

        // 绘制装饰星星
        if (this.active) {
            for (var i = 0; i < GameOverPanel.config.NUM_STARS; i++) {
                this.canvasCtx.drawImage(
                    Runner.imageSprite,
                    this.stars[i].sourceX, this.stars[i].sourceY,
                    starSize, starSize,
                    Math.round(this.stars[i].x), this.stars[i].y,
                    starSize, starSize
                );
            }
        }

        // 绘制 "GAME OVER" 文字
        this.canvasCtx.drawImage(
            Runner.imageSprite,
            textX, this.textImgPos.y,
            textWidth, textHeight,
            Math.round(this.scrollY), this.yPos,
            textWidth, GameOverPanel.config.TEXT_HEIGHT
        );

        // 绘制重启按钮
        this.canvasCtx.drawImage(
            Runner.imageSprite,
            this.restartImgPos.x, this.restartImgPos.y,
            GameOverPanel.config.RESTART_WIDTH, GameOverPanel.config.RESTART_HEIGHT,
            Math.round(this.scrollY + this.dimensions.WIDTH / 2 - GameOverPanel.config.RESTART_WIDTH / 2),
            this.yPos + 40,
            GameOverPanel.config.RESTART_WIDTH, GameOverPanel.config.RESTART_HEIGHT
        );

        this.canvasCtx.globalAlpha = 1;
        this.canvasCtx.restore();
    };

    /**
     * 放置装饰星星
     */
    GameOverPanel.prototype.placeStars = function() {
        var segmentSize = Math.round(this.dimensions.WIDTH / GameOverPanel.config.NUM_STARS);
        for (var i = 0; i < GameOverPanel.config.NUM_STARS; i++) {
            this.stars[i] = {};
            this.stars[i].x = getRandomNum(segmentSize * i, segmentSize * (i + 1));
            this.stars[i].y = getRandomNum(0, GameOverPanel.config.STAR_MAX_Y);
            this.stars[i].sourceX = GameOverPanel.digitYPositions[i] + 9 * i;
        }
    };

    /**
     * 重置
     */
    GameOverPanel.prototype.reset = function() {
        this.scrollY = 0;
        this.score = 0;
        this.update(false);
    };

    // ==================== 启动游戏 ====================

    /**
     * DOM加载完成后初始化游戏
     */
    function onDocumentLoad() {
        new Runner('.interstitial-wrapper');
    }

    document.addEventListener('DOMContentLoaded', onDocumentLoad);

})();