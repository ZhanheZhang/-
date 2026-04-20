from ultralytics import YOLO
import torch


def train_model():
# 从自定义的 YAML 文件构建模型结构
    model = YOLO('yolov8n-faster.yaml')


    try:
        model.load('yolov8n.pt')
        print("成功加载部分预训练权重！")
    except Exception as e:
        print(f"提示：无法完全加载预训练权重{e}")

    # 3. 开始训练
    results = model.train(
        data='D:\RflySim\RflySimAPIs\我的实验\Car&Garbage\Car-Garbage.v1i.yolov8\data.yaml',  # 你的 data.yaml 的相对或绝对路径
        epochs=100,  # 训练轮数
        imgsz=640,  # 训练图片尺寸
        batch=8,
        device='0' if torch.cuda.is_available() else 'cpu',  # 自动选择显卡
        project='runs/train',  # 训练结果保存目录
        name='yolov8n_faster_car_garbage',  # 本次实验的名字
        workers=4,  # 数据加载线程数
        patience=30,  # 容忍 30 轮 mAP 不提升则早停
        save=True,  # 保存模型
        plots=True,  # 绘制训练曲线图
        # 如果你数据里有无人机远景图（目标极小），可以加入下面两行增强：
        # mosaic=1.0,
        # close_mosaic=10
    )

    return results


if __name__ == '__main__':
    # 保证在 Windows 环境下多线程能够正常启动
    import multiprocessing

    multiprocessing.freeze_support()

    print("开始训练基于 FasterNet 轻量化骨架的 YOLOv8...")
    results = train_model()
    print("训练完成！")