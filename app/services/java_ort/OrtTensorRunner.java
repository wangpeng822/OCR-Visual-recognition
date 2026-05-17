import ai.onnxruntime.OnnxTensor;
import ai.onnxruntime.OnnxValue;
import ai.onnxruntime.OrtEnvironment;
import ai.onnxruntime.OrtSession;
import ai.onnxruntime.TensorInfo;

import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.FloatBuffer;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.Collections;

public class OrtTensorRunner {
    public static void main(String[] args) throws Exception {
        if (args.length != 5) {
            throw new IllegalArgumentException("Usage: OrtTensorRunner <model> <shape> <input.bin> <output.bin> <output_shape.txt>");
        }

        String modelPath = args[0];
        long[] shape = parseShape(args[1]);
        Path inputPath = Paths.get(args[2]);
        Path outputPath = Paths.get(args[3]);
        Path shapePath = Paths.get(args[4]);

        float[] input = readFloatArray(inputPath);
        int expected = elementCount(shape);
        if (input.length != expected) {
            throw new IllegalArgumentException("Input float count mismatch. expected=" + expected + " actual=" + input.length);
        }

        OrtEnvironment env = OrtEnvironment.getEnvironment();
        OrtSession.SessionOptions options = new OrtSession.SessionOptions();
        try (OrtSession session = env.createSession(modelPath, options)) {
            String inputName = session.getInputNames().iterator().next();
            try (OnnxTensor tensor = OnnxTensor.createTensor(env, FloatBuffer.wrap(input), shape);
                 OrtSession.Result result = session.run(Collections.singletonMap(inputName, tensor))) {

                OnnxValue value = result.get(0);
                TensorInfo info = (TensorInfo) value.getInfo();
                long[] outShape = info.getShape();
                float[] output = extractFloatArray(value.getValue());
                writeFloatArray(outputPath, output);
                Files.writeString(shapePath, shapeToString(outShape));
            }
        }
    }

    private static long[] parseShape(String value) {
        String[] parts = value.split(",");
        long[] shape = new long[parts.length];
        for (int i = 0; i < parts.length; i++) {
            shape[i] = Long.parseLong(parts[i].trim());
        }
        return shape;
    }

    private static int elementCount(long[] shape) {
        long total = 1;
        for (long dim : shape) {
            total *= dim;
        }
        if (total > Integer.MAX_VALUE) {
            throw new IllegalArgumentException("Tensor is too large");
        }
        return (int) total;
    }

    private static float[] readFloatArray(Path path) throws IOException {
        byte[] bytes = Files.readAllBytes(path);
        FloatBuffer buffer = ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN).asFloatBuffer();
        float[] data = new float[buffer.remaining()];
        buffer.get(data);
        return data;
    }

    private static void writeFloatArray(Path path, float[] values) throws IOException {
        ByteBuffer buffer = ByteBuffer.allocate(values.length * Float.BYTES).order(ByteOrder.LITTLE_ENDIAN);
        for (float value : values) {
            buffer.putFloat(value);
        }
        Files.write(path, buffer.array());
    }

    private static String shapeToString(long[] shape) {
        StringBuilder builder = new StringBuilder();
        for (int i = 0; i < shape.length; i++) {
            if (i > 0) {
                builder.append(',');
            }
            builder.append(shape[i]);
        }
        return builder.toString();
    }

    private static float[] extractFloatArray(Object value) {
        if (value instanceof float[] data) {
            return data;
        }
        if (value instanceof float[][] data) {
            int total = 0;
            for (float[] row : data) {
                total += row.length;
            }
            float[] out = new float[total];
            int offset = 0;
            for (float[] row : data) {
                System.arraycopy(row, 0, out, offset, row.length);
                offset += row.length;
            }
            return out;
        }
        if (value instanceof float[][][] data) {
            int total = 0;
            for (float[][] level2 : data) {
                for (float[] row : level2) {
                    total += row.length;
                }
            }
            float[] out = new float[total];
            int offset = 0;
            for (float[][] level2 : data) {
                for (float[] row : level2) {
                    System.arraycopy(row, 0, out, offset, row.length);
                    offset += row.length;
                }
            }
            return out;
        }
        if (value instanceof float[][][][] data) {
            int total = 0;
            for (float[][][] level3 : data) {
                for (float[][] level2 : level3) {
                    for (float[] row : level2) {
                        total += row.length;
                    }
                }
            }
            float[] out = new float[total];
            int offset = 0;
            for (float[][][] level3 : data) {
                for (float[][] level2 : level3) {
                    for (float[] row : level2) {
                        System.arraycopy(row, 0, out, offset, row.length);
                        offset += row.length;
                    }
                }
            }
            return out;
        }
        throw new IllegalArgumentException("Unsupported output type: " + value.getClass());
    }
}
