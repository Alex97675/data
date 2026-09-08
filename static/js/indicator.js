// --- EMA & MACD TOOTOOLOL ---
function calculateEMA(data, period) {
    let k = 2 / (period + 1);
    let emaArray = [];
    let prevEMA = null;
    for (let i = 0; i < data.length; i++) {
        let val = data[i];
        if (prevEMA === null) {
            prevEMA = val;
        } else {
            prevEMA = (val * k) + (prevEMA * (1 - k));
        }
        emaArray.push(prevEMA);
    }
    return emaArray;
}

function calculateMACD(closes) {
    let ema12 = calculateEMA(closes, 12);
    let ema26 = calculateEMA(closes, 26);
    let macdLine = [];
    for (let i = 0; i < closes.length; i++) {
        macdLine.push(ema12[i] - ema26[i]);
    }
    let signalLine = calculateEMA(macdLine, 9);
    let histogram = [];
    for (let i = 0; i < closes.length; i++) {
        histogram.push(macdLine[i] - signalLine[i]);
    }
    return { macdLine, signalLine, histogram };
}

// --- MACD ZURAH FUNKC ---
function drawMACD(ctx, data, padding, chartWidth, chartHeight, candleWidth) {
    const closes = data.map(d => d[4]);
    const macdData = calculateMACD(closes);

    const mainChartHeight = chartHeight * 0.75;
    const macdTop = padding + mainChartHeight + 20;
    const macdHeight = chartHeight * 0.25 - 20;

    const macdValues = [...macdData.macdLine, ...macdData.signalLine, ...macdData.histogram];
    let maxMacd = Math.max(...macdValues, 0);
    let minMacd = Math.min(...macdValues, 0);
    if (maxMacd === minMacd) { maxMacd = 1; minMacd = -1; }

    const macdToY = val => macdTop + macdHeight - ((val - minMacd) / (maxMacd - minMacd)) * macdHeight;

    // Тусгаарлах шугам
    ctx.strokeStyle = "#1f2630";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(padding, macdTop);
    ctx.lineTo(padding + chartWidth, macdTop);
    ctx.stroke();

    // Histogram
    data.forEach((d, i) => {
        const x = padding + i * candleWidth;
        const hVal = macdData.histogram[i];
        const yZero = macdToY(0);
        const yVal = macdToY(hVal);

        ctx.fillStyle = hVal >= 0 ? "#0ecb81" : "#f6465d";
        ctx.fillRect(x + candleWidth * 0.1, Math.min(yZero, yVal), candleWidth * 0.8, Math.abs(yZero - yVal));
    });

    // MACD Line
    ctx.strokeStyle = "#2962ff";
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    data.forEach((d, i) => {
        const x = padding + i * candleWidth + candleWidth / 2;
        const y = macdToY(macdData.macdLine[i]);
        if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    });
    ctx.stroke();

    // Signal Line
    ctx.strokeStyle = "#ff9800";
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    data.forEach((d, i) => {
        const x = padding + i * candleWidth + candleWidth / 2;
        const y = macdToY(macdData.signalLine[i]);
        if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    });
    ctx.stroke();
}
